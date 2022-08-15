import collections
import os.path
import re
import time
import traceback
from ctypes import *
# 更高效，但不便于跨进程使用，待有性能要求时可以考虑deque
from collections import deque

import cv2
import func_timeout
import numpy as np
from func_timeout import func_set_timeout
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.execption.outer.error_code.camera import NoSrc, CameraInitFail, CameraInUse
from app.v1.Cuttle.basic.MvImport.HK_import import *
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.setting import *
from app.execption.outer.error_code.imgtool import CameraNotResponse
from app.config.setting import HARDWARE_MAPPING_LIST
from app.libs import image_utils
from redis_init import redis_client
from app.v1.Cuttle.basic.hand_serial import CameraPower

MoveToPress = 9
ImageNumberFile = "__number.txt"
GET_ONE_FRAME_TIMEOUT = 5


# 相机初始化
def camera_start(camera_id, device_object, **kwargs):
    # 相机初始化
    redis_client.set(f"g_bExit_{camera_id}", "0")
    # 根据camera_id来支持多摄像头的方案
    print('camera_id:', camera_id)
    try:
        camera_dq_key = device_object.pk + camera_id
        # 先销毁
        if camera_dq_dict.get(camera_dq_key) is not None:
            del camera_dq_dict[camera_dq_key]
        # 为了保证后续操作的统一性，将图片统一放到队列中
        dq = deque(maxlen=CameraMax)
        camera_dq_dict[camera_dq_key] = dq

        temporary = kwargs.get('temporary', True)
        response = camera_init_hk(camera_id, device_object, **kwargs)
        print("half done  has camera? ", device_object.has_camera, 'temporary:', temporary)

        if temporary is True:
            @func_set_timeout(timeout=GET_ONE_FRAME_TIMEOUT)
            def _inner_func():
                return camera_start_hk(camera_id, dq, *response, temporary=temporary)

            _inner_func()
        else:
            camera_start_hk(camera_id, dq, *response, temporary=temporary)

    except Exception as e:
        print('相机初始化异常：', e)
        print(traceback.format_exc())
        raise e
    except func_timeout.exceptions.FunctionTimedOut as e:
        print('获取图片超时了！！！')
        raise e
    finally:
        cam_obj = CamObjList[camera_id] if camera_id in CamObjList else None

        # 统计帧率
        stParam = MVCC_FLOATVALUE()
        memset(byref(stParam), 0, sizeof(MVCC_FLOATVALUE))
        check_result(cam_obj.MV_CC_GetFloatValue, "ResultingFrameRate", stParam)
        print(f'camera{camera_id}原始帧率是：', stParam.fCurValue, '^' * 10)

        pic_count = len(camera_dq_dict[camera_dq_key])
        if pic_count > 1:
            begin_time = camera_dq_dict[camera_dq_key][0]['host_timestamp']
            end_time = camera_dq_dict[camera_dq_key][-1]['host_timestamp']
            frame_rate = pic_count / ((end_time - begin_time) / 1000)
            print(f'camera{camera_id}帧率是：', int(frame_rate), '^' * 10, pic_count, ((end_time - begin_time) / 1000))

        if cam_obj is not None:
            stop_camera(cam_obj, camera_id, **kwargs)

        # 结束循环，关闭取图
        redis_client.set(f"g_bExit_{camera_id}", "1")


def camera_init_hk(camera_id, device_object, **kwargs):
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

        check_result(CamObj.MV_CC_OpenDevice, 1, 0)
        # CamObj.MV_CC_CloseDevice()
        # CamObj.MV_CC_DestroyHandle()
        # check_result(CamObj.MV_CC_OpenDevice, 5, 0)

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

    if kwargs.get('sync_camera'):
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
        if int(device_object.x1) == int(device_object.x2) == 0:
            pass
        else:
            # 这里的4和16是软件设置的时候，必须是4和16的倍数
            width = int(device_object.roi_x2) - int(device_object.roi_x1)
            offset_x = int(device_object.roi_x1)
            height = int(device_object.roi_y2) - int(device_object.roi_y1)
            offset_y = int(device_object.roi_y1)
            print('设置的roi是：', width, height, offset_x, offset_y)
            check_result(CamObj.MV_CC_SetIntValue, 'Width', width)
            check_result(CamObj.MV_CC_SetIntValue, 'Height', height)
            check_result(CamObj.MV_CC_SetIntValue, 'OffsetX', offset_x)
            check_result(CamObj.MV_CC_SetIntValue, 'OffsetY', offset_y)

    check_result(CamObj.MV_CC_StartGrabbing)

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


# temporary：性能测试的时候需要持续不断的往队列里边放图片，但是在其他情况，只需要获取当时的一张截图即可
def camera_start_hk(camera_id, dq, data_buf, n_payload_size, st_frame_info, temporary=True):
    # 这个是海康摄像头持续获取图片的方法，原理还是用ctypes模块调用.dll或者.so文件中的变量
    cam_obj = CamObjList[camera_id]
    # 走到这里以后，设置一个标记，代表相机开始工作了
    redis_client.set(f"camera_loop_{camera_id}", 1)
    while True:
        if redis_client.get(f"g_bExit_{camera_id}") == "1":
            break
        # 这个一个轮询的请求，5毫秒timeout，去获取图片
        ret = cam_obj.MV_CC_GetOneFrameTimeout(byref(data_buf), n_payload_size, st_frame_info, 5)
        if ret == 0:
            camera_snapshot(dq, data_buf, st_frame_info, cam_obj, camera_id)
            if temporary is True:
                redis_client.set(f'g_bExit_{camera_id}', 1)
            else:
                time.sleep(0.001)
        else:
            continue


def camera_snapshot(dq, data_buf, stFrameInfo, cam_obj, camera_id):
    # 当摄像头有最新照片后，创建一个stConvertParam的结构体去获取实际图片和图片信息，
    # pDstBuffer这个指针指向真实图片数据的缓存
    nRGBSize = stFrameInfo.nWidth * stFrameInfo.nHeight * 3
    stConvertParam = MV_CC_PIXEL_CONVERT_PARAM()
    memset(byref(stConvertParam), 0, sizeof(stConvertParam))
    stConvertParam.nWidth = stFrameInfo.nWidth
    stConvertParam.nHeight = stFrameInfo.nHeight
    stConvertParam.pSrcData = data_buf
    stConvertParam.nSrcDataLen = stFrameInfo.nFrameLen
    stConvertParam.enSrcPixelType = stFrameInfo.enPixelType
    stConvertParam.enDstPixelType = PixelType_Gvsp_BGR8_Packed
    content = (c_ubyte * nRGBSize)()
    stConvertParam.pDstBuffer = content
    stConvertParam.nDstBufferSize = nRGBSize
    cam_obj.MV_CC_ConvertPixelType(stConvertParam)
    # 得到图片做最简单处理就放入deque,这块不要做旋转等操作，否则跟不上240帧的获取速度
    image = np.asarray(content, dtype="uint8")
    image = image.reshape((stFrameInfo.nHeight, stFrameInfo.nWidth, 3))
    frame_num = stFrameInfo.nFrameNum
    dq.append({'image': image,
               'host_timestamp': stFrameInfo.nHostTimeStamp,
               'frame_num': frame_num})
    del content
    del image
    del data_buf
    print(f'camera{camera_id}获取到图片了', frame_num)
    # 还有一个条件可以终止摄像机获取图片，就是每次获取的图片数量有个最大值，超过了最大值，本次获取必须终止，否则内存太大
    if frame_num >= CameraMax:
        print('达到了取图的最大限制！！！')
        redis_client.set(f'g_bExit_{camera_id}', 1)


def stop_camera(cam_obj, camera_id, **kwargs):
    print('stop grabbing..........', kwargs.get('feature_test'))
    cam_obj.MV_CC_StopGrabbing()
    # 性能测试的时候销毁，用来释放内存
    if not kwargs.get('feature_test'):
        print('开始销毁。。。。。。。。。。。。')
        cam_obj.MV_CC_CloseDevice()
        cam_obj.MV_CC_DestroyHandle()
        # 销毁
        del cam_obj
        del CamObjList[camera_id]
    print("stop camera finished..[Debug]")


def check_result(func, *args):
    return_value = func(*args)
    if return_value != 0:
        print("return_value", hex(return_value), *args, func.__name__)
        raise CameraInitFail


def get_camera_ids():
    camera_ids = []
    for camera_id in HARDWARE_MAPPING_LIST:
        if not camera_id.isdigit():
            continue
        camera_ids.append(camera_id)
    return camera_ids


class CameraHandler(Handler):
    Function = collections.namedtuple("Function", ["condition", "function", "regex"])
    # 这个Function namedtuple是用做adb的结果后处理，根据结果对应匹配后处理函数，最后一个是带入函数的参数
    function_list = [
        Function("shell screencap", "snap_shot", ""),
        Function("shell screenrecord", "get_video", re.compile("--time-limit (.*?) ")),
        Function("shell rm", "ignore", ""),
        Function("pull", "move", re.compile("pull .*? (.*)")),
        Function("exec-out screencap", "screen_shot_and_pull", re.compile("screencap -p > (.*)"))
    ]

    def __init__(self, *args, **kwargs):
        super(CameraHandler, self).__init__(*args, **kwargs)
        # 是否获取高曝光图片
        self.high_exposure = kwargs.get('high_exposure')
        # 是否获取原始图片，非roi图片
        self.original = kwargs.get('original')
        # 摄像机录像
        self.record_video = kwargs.get('record_video')
        self.record_time = kwargs.get('record_time') or 1
        # 性能测试的时候，用来实时的存放图片，如果传入这个参数，则可以实时的获取dp里边的图片
        self.back_up_dq = kwargs.get('back_up_dq')
        self.modify_fps = kwargs.get("modify_fps")
        # 图片拼接时候用到的几个参数
        self.x_min = None
        self.y_min = None
        self.x_max = None
        self.y_max = None
        self.pts = None
        self.weights = None

    def before_execute(self, **kwargs):
        # 解析adb指令，区分拍照还是录像
        self.exec_content, opt_type = self.grouping(self.exec_content)
        self.str_func = getattr(self, opt_type)
        return normal_result

    def grouping(self, content):
        for condition, function, regex in self.function_list:
            if condition in content:
                res = re.search(regex, content)
                return res.group(1) if res.group() else "", function
        return "", "ignore"

    def snap_shot(self):
        # 摄像头数量不一样的时候，方案不同
        camera_ids = get_camera_ids()

        futures = []
        temporary = False if len(camera_ids) > 1 else self.back_up_dq is None
        sync_camera = True if len(camera_ids) > 1 else False
        # 如果录像的话，则按照性能测试来录像
        feature_test = False if self.record_video else self.back_up_dq is None
        for camera_id in camera_ids:
            redis_client.set(f"camera_loop_{camera_id}", 0)
            # 相机正在获取图片的时候 不能再次使用
            if redis_client.get(f"g_bExit_{camera_id}") == "0":
                raise CameraInUse()

            executer = ThreadPoolExecutor()
            future = executer.submit(camera_start,
                                     camera_id,
                                     self._model,
                                     high_exposure=self.high_exposure,
                                     temporary=temporary,
                                     original=self.original,
                                     sync_camera=sync_camera,
                                     feature_test=feature_test,
                                     modify_fps=self.modify_fps)
            if camera_id not in CamObjList and camera_id != camera_ids[-1]:
                # 必须等待一段时间 同时初始化有bug发生 以后解决吧
                time.sleep(0.5)
            futures.append(future)

        # 默认使用第一个相机中的截图
        if len(camera_ids) == 1:
            image = None
            # 实时的获取到图片
            if self.back_up_dq is not None:
                # empty_times = 0
                # 停止时刻由外部进行控制，这里负责图像处理即可
                while get_global_value(CAMERA_IN_LOOP):
                    time.sleep(0.5)
                    # try:
                    #     image_info = camera_dq_dict.get(self._model.pk + camera_ids[0]).popleft()
                    #     image = image_info['image']
                    #     print('帧号：', image_info['frame_num'])
                    #     image = np.rot90(self.get_roi(image, False), 3)
                    #     self.back_up_dq.append({'image': image, 'host_timestamp': image_info['host_timestamp']})
                    #     empty_times = 0
                    # except IndexError:
                    #     # 拿的速度太快的话可能还没有存进去
                    #     if redis_client.get(f"g_bExit_{camera_ids[0]}") == "0":
                    #         time.sleep(1)
                    #     empty_times += 1
                    #     if empty_times > 3:
                    #         print('相机没图片了')
                    #         break
                redis_client.set(f"g_bExit_{camera_ids[0]}", "1")
                for _ in as_completed(futures):
                    print('已经停止获取图片了')
            else:
                for _ in as_completed(futures):
                    image = camera_dq_dict.get(self._model.pk + camera_ids[0])[-1]['image']
                    # 读取矫正参数
                    # f = pickle.load(open('app/config/camera_correct', 'rb'))
                    # ret, mtx, dist, rvecs, tvecs = f['ret'], f['mtx'], f['dist'], f['rvecs'], f['tvecs']
                    # h, w = image.shape[:2]
                    # new_camera_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
                    # image = cv2.undistort(image, mtx, dist, None, new_camera_mtx)
                    if not self.original:
                        image = np.rot90(self.get_roi(image, False), 3)

                try:
                    self.src = image
                except UnboundLocalError:
                    raise CameraNotResponse

                # 清空内存
                print('清空 camera_dq_dict 内存')
                camera_dq_dict.get(self._model.pk + camera_ids[0]).clear()
        else:
            # 判断俩个相机都已经进入到了循环中
            while True:
                all_in_loop = True
                for camera_id in camera_ids:
                    # 注意这里是字符串
                    if redis_client.get(f"camera_loop_{camera_id}") == '0':
                        all_in_loop = False
                        break
                if all_in_loop:
                    break

            need_back_up_dq = True
            if self.high_exposure:
                timeout = 0.4
            else:
                timeout = 0.1
            # 实时的获取到图片
            if self.back_up_dq is not None:
                need_back_up_dq = False
                # 发送同步信号
                with CameraPower(timeout=timeout):
                    empty_times = 0
                    while get_global_value(CAMERA_IN_LOOP):
                        # 必须等待，否则while死循环导致其他线程没有机会执行
                        if redis_client.get(f"g_bExit_{camera_ids[0]}") == "0":
                            time.sleep(1)
                        if get_global_value(CAMERA_IN_LOOP):
                            # 判断图片是否全部处理完毕
                            if self.merge_frame(camera_ids, 60) == -1:
                                empty_times += 1
                                if empty_times > 3:
                                    break
                            else:
                                empty_times = 0
                # 后续再保存一些图片，因为结束点之后还需要一些图片
                self.merge_frame(camera_ids, 60)
                # 如果依然在loop中，也就是达到了取图的最大限制，还没来得及处理图片，则把剩下的图片都合成完毕
                if get_global_value(CAMERA_IN_LOOP):
                    self.merge_frame(camera_ids, 60)
            else:
                if self.record_video:
                    timeout = self.record_time
                # 发送同步信号
                with CameraPower(timeout=timeout):
                    pass

            for camera_id in camera_ids:
                redis_client.set(f"g_bExit_{camera_id}", "1")
            for _ in as_completed(futures):
                print('已经停止获取图片了')

            # 最后再统一处理图片
            if need_back_up_dq:
                self.back_up_dq = []
                self.merge_frame(camera_ids)
                self.back_up_dq.clear()

            # 清空图片内存
            for camera_id in camera_ids:
                camera_dq_dict[self._model.pk + camera_id].clear()

        # 记录一下拼接以后的图片大小，后边计算的时候需要用到，只在第一次拼接的时候写入，在重置h矩阵的时候，需要将这个值删除
        if self.original and self.src is not None:
            merge_shape = get_global_value('merge_shape')
            if merge_shape is None:
                set_global_value('merge_shape', self.src.shape)
                with open(COORDINATE_CONFIG_FILE, 'at') as f:
                    f.writelines(f'merge_shape={self.src.shape}\n')

        return 0

    def merge_frame(self, camera_ids, merge_number=None):
        # 这里保存的就是同一帧拍摄的所有图片
        self.frames = collections.defaultdict(list)

        # 先合并指定数量的图片
        camera_length = min([len(camera_dq_dict.get(self._model.pk + camera_id))
                             for camera_id in camera_ids])
        if merge_number is None:
            merge_number = camera_length
        else:
            merge_number = merge_number if merge_number < camera_length else camera_length

        # 同步拍照靠硬件解决，这里获取同步的图片以后，直接拼接即可
        cur_frame_num = -1
        frame_index = 0
        # 当前处理的最后一帧一定要满足同步条件，否则后边处理的数据会丢帧
        while (cur_frame_num != -1 and len(self.frames[cur_frame_num]) == 1) or frame_index < merge_number:
            try:
                for camera_id in camera_ids:
                    # 在这里进行运算，选出一张图片，赋给self.src
                    src = camera_dq_dict.get(self._model.pk + camera_id).popleft()
                    # 记录来源于哪个相机，方便后续处理
                    src['camera_id'] = camera_id
                    self.frames[src['frame_num']].append(src)
                    cur_frame_num = src['frame_num']
                    frame_index += 1
            except IndexError:
                # 如果有一个没有图了，直接退出，这样只是丢有限的几张图，后边能同步过来就ok
                break

        if len(self.frames) == 0:
            return -1

        self.get_syn_frame(camera_ids)

        if len(self.back_up_dq) > 0:
            image = self.back_up_dq[0]['image']
            self.src = image

            # 写入到文件夹中，测试用
            if self.record_video:
                if os.path.exists('camera'):
                    import shutil
                    shutil.rmtree('camera')
                    os.mkdir('camera')
                else:
                    os.mkdir('camera')

        # 清理内存
        self.frames.clear()

    def get_roi(self, src, multi=True):
        if int(self._model.y1) == 0 and int(self._model.y2) == 0 and int(self._model.x1) == 0 and int(
                self._model.x2) == 0:
            return src
        if multi:
            # 只针对多摄像机，多摄像机没有把参数设置到摄像机上，后续有需求可以直接设置到相机的参数上
            return src[int(self._model.y1):int(self._model.y2), int(self._model.x1):int(self._model.x2)]
        else:
            # 硬件roi获取的是一个较大的区域，需要再次通过软件roi将区域缩到用户设置的roi大小
            return src[int(self._model.y1) - int(self._model.roi_y1): int(self._model.y2) - int(self._model.roi_y1),
                       int(self._model.x1) - int(self._model.roi_x1): int(self._model.x2) - int(self._model.roi_x1)]

    # 从多个相机中获取同步的内容
    def get_syn_frame(self, camera_ids):
        # 判断是否丢帧
        lost_frame_nums = []

        h = get_global_value(MERGE_IMAGE_H)
        for frame_num, frames in self.frames.items():
            if len(frames) != len(camera_ids):
                lost_frame_nums.append(frame_num)
                del frames
                continue

            # 目前只支持拼接俩个相机的数据 1和2中的数据不能乱，因为h矩阵不同
            if int(frames[0]['camera_id']) < int(frames[1]['camera_id']):
                img1 = frames[0]['image']
                img2 = frames[1]['image']
            else:
                img2 = frames[0]['image']
                img1 = frames[1]['image']
            # 有时候俩个相机反了，打开这里
            # if CORAL_TYPE == 5.3:
            #     img1, img2 = img2, img1

            host_t_1 = frames[0]['host_timestamp']
            host_t_2 = frames[1]['host_timestamp']
            print(frame_num, host_t_2 - host_t_1)

            if h is None:
                # 调试的时候打开
                # cv2.imwrite('camera/camera_1.png', img1)
                # cv2.imwrite('camera/camera_2.png', img2)
                h = self.get_homography(img1, img2)

            result = self.warp_two_images(img2, img1, h)

            if not self.original:
                if CORAL_TYPE == 5.3:
                    result = np.rot90(self.get_roi(result))
                else:
                    result = np.rot90(self.get_roi(result), 3)

            self.back_up_dq.append({'image': result, 'host_timestamp': host_t_1})
            del result

        if lost_frame_nums:
            print('发生了丢帧:', lost_frame_nums, '&' * 10)

    @staticmethod
    def get_homography(img1, img2):
        # 先读取缓存中的矩阵，没有的话再重新生成
        h = get_global_value(MERGE_IMAGE_H)
        if h is None:
            # 判断是否有文件，有的话从文件中读出来，赋值给全局的变量，没有的话现生成一个，然后保存到文件中（方便柜子之间拷贝）。最后还需要提供一个接口，可以删除这个文件，重置全局变量
            if os.path.exists(MERGE_IMAGE_H):
                h = np.load(MERGE_IMAGE_H, allow_pickle=True)
            else:
                h = image_utils.get_homography(img1, img2)
                np.save(MERGE_IMAGE_H, h)
            set_global_value(MERGE_IMAGE_H, h)
        del img1, img2
        return h

    def warp_two_images(self, img1, img2, h):
        h1, w1 = img1.shape[:2]
        if self.pts is None:
            # 有些参数应该只计算一遍，这样加快处理速度
            h2, w2 = img2.shape[:2]
            pts1 = np.float32([[0, 0], [0, h1], [w1, h1], [w1, 0]]).reshape(-1, 1, 2)
            pts2 = np.float32([[0, 0], [0, h2], [w2, h2], [w2, 0]]).reshape(-1, 1, 2)
            pts2_ = cv2.perspectiveTransform(pts2, h)
            pts = np.concatenate((pts1, pts2_), axis=0)
            # print(pts)
            [x_min, y_min] = np.int32(pts.min(axis=0).ravel() - 0.5)
            [x_max, y_max] = np.int32(pts.max(axis=0).ravel() + 0.5)

            # 把数据保存一下，下次直接使用
            self.x_min = x_min
            self.y_min = y_min
            self.x_max = x_max
            self.y_max = y_max
            self.pts = pts

        t = [-self.x_min, -self.y_min]
        ht = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]])

        result = cv2.warpPerspective(img2, ht.dot(h), (self.x_max - self.x_min, self.y_max - self.y_min))
        # cv2.imwrite('D:\\code\\coral-local\\camera\\result_1.png', result)

        result_copy = np.array(result)
        result[t[1]:h1 + t[1], t[0]:w1 + t[0]] = img1
        # print(t)

        sorted_pts = [(int(pos[0][0] + t[0]), int(pos[0][1] + t[1])) for pos in self.pts]
        # 5D的相机组装方式不一样
        if CORAL_TYPE == 5.3:
            sorted_pts = sorted(sorted_pts, key=lambda x: x[1])[2:6]
        else:
            # 取中间的四个点
            sorted_pts = sorted(sorted_pts)[2:6]
        # 调试的时候打开
        # for pos in sorted_pts:
        #     cv2.circle(result, pos, 10, (0, 0, 255), -1)

        sorted_pts = np.array(sorted_pts)
        merge_min_x, merge_min_y = sorted_pts.min(axis=0).ravel()
        merge_max_x, merge_max_y = sorted_pts.max(axis=0).ravel()
        # print(sorted_pts)
        # print(merge_min_x, merge_min_y)
        # print(merge_max_x, merge_max_y)

        if CORAL_TYPE == 5.3:
            # 最耗时的地方，所以提前计算出来权重
            if self.weights is None:
                self.weights = np.ones(result.shape)
                for y in range(merge_min_y, merge_max_y):
                    weight = (y - merge_min_y) / (merge_max_y - merge_min_y)
                    result[y, merge_min_x: merge_max_x, :] = result_copy[y, merge_min_x: merge_max_x, :] * (
                            1 - weight) + result[y, merge_min_x: merge_max_x, :] * weight
                    self.weights[y, merge_min_x: merge_max_x, :] = 1 - weight
            else:
                result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] = \
                    result_copy[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                    self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] + \
                    result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                    (1 - self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :])
        else:
            if self.weights is None:
                self.weights = np.ones(result.shape)
                for r in range(merge_min_x, merge_max_x):
                    weight = (r - merge_min_x) / (merge_max_x - merge_min_x)
                    if t[0] < merge_min_x:
                        result[merge_min_y: merge_max_y, r, :] = \
                            result_copy[merge_min_y: merge_max_y, r, :] * \
                            weight + result[merge_min_y: merge_max_y, r, :] * (1 - weight)
                    else:
                        result[merge_min_y: merge_max_y, r, :] = \
                            result_copy[merge_min_y: merge_max_y, r, :] * \
                            (1 - weight) + result[merge_min_y: merge_max_y, r, :] * weight
                    self.weights[merge_min_y: merge_max_y, r, :] = weight
            else:
                if t[0] < merge_min_x:
                    result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] = \
                        result_copy[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] + \
                        result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        (1 - self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :])
                else:
                    result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] = \
                        result_copy[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        (1 - self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :]) + \
                        result[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :] * \
                        self.weights[merge_min_y: merge_max_y, merge_min_x: merge_max_x, :]

        return result

    def move(self, *args, **kwargs):
        if hasattr(self, "src") and args[0]:
            cv2.imwrite(args[0], self.src)
            delattr(self, "src")
            return 0
        elif hasattr(self, "video_src") or self.record_video or self.back_up_dq is not None:
            # 暂时注释掉 需要的时候再实现
            pass
            # # 视频分析，存储每一帧图片，并记录总数
            # start = time.time()
            # number = 0
            # total_number = len(self.video_src)
            # with open(get_file_name(args[0]) + ImageNumberFile, "w") as f:
            #     f.write(str(total_number))
            # for i in range(total_number):
            #     cv2.imwrite(get_file_name(args[0]) + f"__{number}.png", self.video_src.popleft())
            #     number += 1
            # delattr(self, "video_src")
            # print("save image time:", time.time() - start)
        else:
            raise NoSrc

    def screen_shot_and_pull(self, *args, **kwargs):
        self.snap_shot()
        self.move(*args)

    def ignore(self, *arg, **kwargs):
        return 0
