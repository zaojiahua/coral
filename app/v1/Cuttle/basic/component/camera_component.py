import time
import traceback
from ctypes import *
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
import func_timeout
import numpy as np
from func_timeout import func_set_timeout

from app.execption.outer.error_code.camera import CameraInitFail
from app.v1.Cuttle.basic.MvImport.HK_import import *
from app.v1.Cuttle.basic.setting import *
from redis_init import redis_client

GET_ONE_FRAME_TIMEOUT = 5
# 统计帧率 多摄的时候，因为在消耗图片的时候，会减少队列中图片的数量，算出来的帧率是某一段时间的帧率，不是拍摄
# 整个过程中的帧率，所以加入这个数据结构，用来做统计，方便调试和测试性能
frame_rate_dict = {}
CamObjList = {}
# 提前开辟图片的内存
collate_content = []
# 图片合成以后，先不要往管道里边放，放入管道是耗时操作，先保存起来，批量放或者开一个线程去放
frame_cache = deque(maxlen=CameraMax)


# 注意这里是单独的一个进程，数据只能自己用，其他进程无法使用，进程间的通信使用queue
# 相机初始化
def camera_start(camera_id, device_label, queue, kwargs_queue, ret_kwargs_queue):
    while True:
        if redis_client.get(f"g_bExit_{camera_id}") == '0':
            # 根据camera_id来支持多摄像头的方案
            print('camera_id:', camera_id)

            try:
                kwargs = {} if kwargs_queue.empty() else kwargs_queue.get()
                print('kwargs', kwargs)

                # 统计帧率
                frame_rate_dict[camera_id] = {'begin_time': -1, 'end_time': -1, 'pic_count': 0}

                # 开一个线程，专门往管道里边放入图片
                frame_cache.clear()
                executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="camera_")
                queue_put_thread = executor.submit(queue_put, camera_id, queue)

                temporary = kwargs.get('temporary', True)
                response = camera_init_hk(camera_id, device_label, **kwargs)
                print("half done camera init", device_label, 'temporary:', temporary)

                # 性能测试的时候提前分配内存 应该单独放到一个队列里边去做
                if not temporary and not kwargs.get('feature_test'):
                    width, height, _, _ = get_roi(device_label, kwargs.get('sync_camera'))
                    if width and height:
                        n_rgb_size = width * height * 3
                        print('size大小是', n_rgb_size)
                        for i in range(int(CameraMax / 3)):
                            collate_content.append((c_ubyte * n_rgb_size)())
                        print('内存提前分配完毕')

                # 开始拍照
                start_grabbing(camera_id)

                if temporary is True:
                    @func_set_timeout(timeout=GET_ONE_FRAME_TIMEOUT)
                    def _inner_func():
                        return camera_start_hk(camera_id, queue, *response, temporary=temporary)

                    _inner_func()
                else:
                    camera_start_hk(camera_id, queue, *response, temporary=temporary)

            except Exception as e:
                print('相机初始化异常：', e)
                print(traceback.format_exc())
            except func_timeout.exceptions.FunctionTimedOut as e:
                print('相机初始化异常，获取图片超时了！！！')
            finally:
                cam_obj = CamObjList[camera_id] if camera_id in CamObjList else None

                # 统计帧率
                if cam_obj is not None:
                    stParam = MVCC_FLOATVALUE()
                    memset(byref(stParam), 0, sizeof(MVCC_FLOATVALUE))
                    check_result(cam_obj.MV_CC_GetFloatValue, "ResultingFrameRate", stParam)
                    print(f'camera{camera_id}原始帧率是：', stParam.fCurValue, '^' * 10)

                pic_count = frame_rate_dict[camera_id]['pic_count']
                if pic_count > 1:
                    begin_time = frame_rate_dict[camera_id]['begin_time']
                    # end_time 可能是达到了取图的最大限制，也可能是用户终止了
                    end_time = frame_rate_dict[camera_id]['end_time']
                    frame_rate = pic_count / ((end_time - begin_time) / 1000)
                    print(f'camera{camera_id}帧率是：', int(frame_rate), '^' * 10, pic_count, ((end_time - begin_time) / 1000))

                if cam_obj is not None:
                    stop_camera(cam_obj, camera_id, **kwargs)

                # 清理提前分配的内存
                collate_content.clear()

                # 结束循环，关闭取图
                redis_client.set(f"g_bExit_{camera_id}", "1")

                for _ in as_completed([queue_put_thread]):
                    pass

                # 等拿图这里完全结束了，另一个进程中再执行其他的操作，这里做一个同步
                ret_kwargs_queue.put('end')
        time.sleep(0.1)


def camera_init_hk(camera_id, device_label, **kwargs):
    inited = False
    if camera_id in CamObjList and CamObjList[camera_id]:
        inited = True
        CamObj = CamObjList[camera_id]

    if not inited:
        print('重新初始化。。。。')
        deviceList = MV_CC_DEVICE_INFO_LIST()
        tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE
        check_result(MvCamera.MV_CC_EnumDevices, tlayerType, deviceList)
        CamObj = MvCamera()
        # index 0--->第一个设备
        stDeviceList = cast(deviceList.pDeviceInfo[int(camera_id) - 1], POINTER(MV_CC_DEVICE_INFO)).contents
        check_result(CamObj.MV_CC_CreateHandle, stDeviceList)

        try:
            check_result(CamObj.MV_CC_OpenDevice, 1, 0)
        except CameraInitFail:
            CamObj.MV_CC_CloseDevice()
            CamObj.MV_CC_DestroyHandle()
            check_result(CamObj.MV_CC_CreateHandle, stDeviceList)
            check_result(CamObj.MV_CC_OpenDevice, 5, 0)

    for key in globals()['camera_params_' + str(int(CORAL_TYPE * 10))]:
        if isinstance(key[1], bool):
            check_result(CamObj.MV_CC_SetBoolValue, key[0], key[1])
        elif len(key) == 3 and key[2] == 'enum':
            check_result(CamObj.MV_CC_SetEnumValue, key[0], key[1])
        elif isinstance(key[1], int):
            check_result(CamObj.MV_CC_SetIntValue, key[0], key[1])
        elif isinstance(key[1], float):
            check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])

    if kwargs.get('high_exposure'):
        for key in high_exposure_params:
            check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])

    if kwargs.get('sync_camera') and not kwargs.get('soft_sync'):
        for key in sync_camera_params:
            if len(key) == 3 and key[2] == 'enum':
                check_result(CamObj.MV_CC_SetEnumValue, key[0], key[1])
            elif isinstance(key[1], float):
                check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])
    else:
        check_result(CamObj.MV_CC_SetEnumValue, 'TriggerMode', 0)

    if kwargs.get("modify_fps") and CORAL_TYPE == 5.2:
        # Tcab-5se在进行性能测试时需要相机帧率
        for key in camera_params_52_performance:
            if len(key) == 3 and key[2] == 'enum':
                check_result(CamObj.MV_CC_SetEnumValue, key[0], key[1])
            elif isinstance(key[1], float):
                check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])

    # 设置roi 多摄像机暂时不设置
    if not kwargs.get('original') and not kwargs.get('sync_camera'):
        width, height, offset_x, offset_y = get_roi(device_label)
        if width and height:
            check_result(CamObj.MV_CC_SetIntValue, 'Width', width)
            check_result(CamObj.MV_CC_SetIntValue, 'Height', height)
            check_result(CamObj.MV_CC_SetIntValue, 'OffsetX', offset_x)
            check_result(CamObj.MV_CC_SetIntValue, 'OffsetY', offset_y)

    # add_node_ret = CamObj.MV_CC_SetImageNodeNum(10)
    # print("增大缓存节点结果", add_node_ret)

    stParam = MVCC_INTVALUE()
    memset(byref(stParam), 0, sizeof(MVCC_INTVALUE))
    check_result(CamObj.MV_CC_GetIntValue, "PayloadSize", stParam)

    nPayloadSize = stParam.nCurValue
    data_buf = (c_ubyte * nPayloadSize)()
    stFrameInfo = MV_FRAME_OUT_INFO_EX()

    if not inited:
        CamObjList[camera_id] = CamObj

    memset(byref(stFrameInfo), 0, sizeof(stFrameInfo))
    return data_buf, nPayloadSize, stFrameInfo


# 获取设置的roi大小
def get_roi(device_label, sync_camera=False):
    width = height = offset_x = offset_y = 0
    # 多相机合并的时候，没有设置roi，原图多大就是多大
    if sync_camera:
        for p_key in globals()['camera_params_' + str(int(CORAL_TYPE * 10))]:
            if p_key[0] == 'Width':
                width = p_key[1]
            elif p_key[0] == 'Height':
                height = p_key[1]
    else:
        from app.v1.device_common.device_model import Device
        device_object = Device(pk=device_label)
        if not device_object.x1 or not device_object.x2 or (int(device_object.x1) == int(device_object.x2) == 0):
            return 0, 0, 0, 0
        else:
            # 这里的4和16是软件设置的时候，必须是4和16的倍数
            width = int(device_object.roi_x2) - int(device_object.roi_x1)
            offset_x = int(device_object.roi_x1)
            height = int(device_object.roi_y2) - int(device_object.roi_y1)
            offset_y = int(device_object.roi_y1)

    print('设置的roi是：', width, height, offset_x, offset_y)
    return width, height, offset_x, offset_y


# 开始拍照
def start_grabbing(camera_id):
    cam_obj = CamObjList[camera_id]
    check_result(cam_obj.MV_CC_StartGrabbing)
    redis_client.set(f"camera_grabbing_{camera_id}", 1)


# temporary：性能测试的时候需要持续不断的往队列里边放图片，但是在其他情况，只需要获取当时的一张截图即可
def camera_start_hk(camera_id, dq, data_buf, n_payload_size, st_frame_info, temporary=True):
    # 这个是海康摄像头持续获取图片的方法，原理还是用ctypes模块调用.dll或者.so文件中的变量
    cam_obj = CamObjList[camera_id]
    # 走到这里以后，设置一个标记，代表相机开始工作了
    redis_client.set(f"camera_loop_{camera_id}", 1)
    while True:
        if redis_client.get(f"camera_grabbing_{camera_id}") != "1":
            continue

        if redis_client.get(f"g_bExit_{camera_id}") == "1":
            break

        # 这个一个轮询的请求，5毫秒timeout，去获取图片
        ret = cam_obj.MV_CC_GetOneFrameTimeout(byref(data_buf), n_payload_size, st_frame_info, 5)
        if ret == 0:
            camera_snapshot(dq, data_buf, st_frame_info, cam_obj, camera_id)
            if temporary is True:
                redis_client.set(f'g_bExit_{camera_id}', 1)
        else:
            continue


def camera_snapshot(dq, data_buf, st_frame_info, cam_obj, camera_id):
    # 当摄像头有最新照片后，创建一个stConvertParam的结构体去获取实际图片和图片信息，
    # pDstBuffer这个指针指向真实图片数据的缓存
    b = time.time()
    n_rgb_size = st_frame_info.nWidth * st_frame_info.nHeight * 3
    st_convert_param = MV_CC_PIXEL_CONVERT_PARAM()
    memset(byref(st_convert_param), 0, sizeof(st_convert_param))
    st_convert_param.nWidth = st_frame_info.nWidth
    st_convert_param.nHeight = st_frame_info.nHeight
    st_convert_param.pSrcData = data_buf
    st_convert_param.nSrcDataLen = st_frame_info.nFrameLen
    st_convert_param.enSrcPixelType = st_frame_info.enPixelType
    st_convert_param.enDstPixelType = PixelType_Gvsp_BGR8_Packed

    # print('11111', (time.time() - b) * 1000)
    # 这一步的操作比较耗时，所以提前分配内存
    if len(collate_content) > 0:
        content = collate_content.pop()
    else:
        content = (c_ubyte * n_rgb_size)()
    # print('22222', (time.time() - b) * 1000)

    st_convert_param.pDstBuffer = content
    st_convert_param.nDstBufferSize = n_rgb_size
    cam_obj.MV_CC_ConvertPixelType(st_convert_param)
    # 得到图片做最简单处理就放入deque,这块不要做旋转等操作，否则跟不上240帧的获取速度
    image = np.asarray(content, dtype="uint8")
    image = image.reshape((st_frame_info.nHeight, st_frame_info.nWidth, 3))
    frame_num = st_frame_info.nFrameNum
    # print('333333', (time.time() - b) * 1000)
    frame_cache.append({'image': image,
                        'host_timestamp': st_frame_info.nHostTimeStamp,
                        'frame_num': frame_num})
    # if frame_num % 2 == 0:
    #     dq.put(frame_cache)
    # print('4444444', (time.time() - b) * 1000)
    del content
    del image
    del data_buf

    # 记录帧率
    frame_rate_dict[camera_id]['pic_count'] += 1
    if frame_num == 0:
        frame_rate_dict[camera_id]['begin_time'] = st_frame_info.nHostTimeStamp
    else:
        frame_rate_dict[camera_id]['end_time'] = st_frame_info.nHostTimeStamp

    print(f'camera{camera_id}获取到图片了', frame_num, ' ' * 5, frame_rate_dict[camera_id]['pic_count'], ' ' * 2, st_frame_info.nHostTimeStamp)
    # print('555555', (time.time() - b) * 1000)
    # 还有一个条件可以终止摄像机获取图片，就是每次获取的图片数量有个最大值，超过了最大值，本次获取必须终止，否则内存太大
    if frame_num >= CameraMax:
        print('达到了取图的最大限制！！！')
        redis_client.set(f'g_bExit_{camera_id}', 1)


# 单独的一个线程，往管道里边放入图片
def queue_put(camera_id, dq):
    while True:
        # 只要有数据就放入
        while len(frame_cache) > 0:
            dq.put(frame_cache.popleft())
            time.sleep(0.01)

        # 取图结束的时候，线程结束
        if redis_client.get(f'g_bExit_{camera_id}') == '1':
            # 把剩余的图片，全部放入到管道中
            while len(frame_cache) > 0:
                dq.put(frame_cache.popleft())
            frame_cache.clear()
            break
        time.sleep(0.1)
    print('相机中放入管道的线程结束。。。')


def stop_camera(cam_obj, camera_id, **kwargs):
    ret = cam_obj.MV_CC_StopGrabbing()
    print(f'stop grabbing..........{ret}', kwargs.get('feature_test'))
    # 性能测试的时候销毁，用来释放内存
    if not kwargs.get('feature_test'):
        print('开始销毁。。。。。。。。。。。。')
        # cam_obj.MV_CC_CloseDevice()
        # cam_obj.MV_CC_DestroyHandle()
        # # 销毁
        # del cam_obj
        # del CamObjList[camera_id]
    print("stop camera finished..[Debug]")


def check_result(func, *args):
    return_value = func(*args)
    if return_value != 0:
        print("return_value", hex(return_value), *args, func.__name__)
        raise CameraInitFail
