import collections
import os.path
import re
import time
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
from app.v1.Cuttle.basic.common_utli import get_file_name
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.setting import camera_dq_dict, normal_result, CameraMax, \
    camera_params_240, CamObjList, camera_params_feature, high_exposure_params, high_exposure_params_feature, \
    sync_camera_params, get_global_value, set_global_value, MERGE_IMAGE_H, COORDINATE_CONFIG_FILE
from app.execption.outer.error_code.imgtool import CameraNotResponse
from app.config.setting import HARDWARE_MAPPING_LIST
from app.libs import image_utils
from redis_init import redis_client
from app.v1.Cuttle.basic.hand_serial import CameraUsbPower

MoveToPress = 9
ImageNumberFile = "__number.txt"
GET_ONE_FRAME_TIMEOUT = 5


# 相机初始化
def camera_start(camera_id, device_object, **kwargs):
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
        # 性能测试相机初始化
        redis_client.set(f"g_bExit_{camera_id}", "0")

        if CORAL_TYPE in [5, 5.3]:
            response = camera_init_hk(camera_id, device_object, **kwargs)
            temporary = kwargs.get('temporary', True)
            print("half done  has camera? ", device_object.has_camera, 'temporary:', temporary)
        else:
            # 功能测试相机初始化
            kwargs['feature_test'] = True
            response = camera_init_hk(camera_id, device_object, **kwargs)
            temporary = True
            print("has camera?", device_object.has_camera)

        if temporary is True:
            @func_set_timeout(timeout=GET_ONE_FRAME_TIMEOUT)
            def _inner_func():
                return camera_start_hk(camera_id, dq, *response, temporary=temporary)

            _inner_func()
        else:
            camera_start_hk(camera_id, dq, *response, temporary=temporary)

    except Exception as e:
        print('相机初始化异常：', e)
        raise e
    except func_timeout.exceptions.FunctionTimedOut as e:
        print('获取图片超时了！！！')
        raise e
    finally:
        # 结束循环，关闭取图
        redis_client.set(f"g_bExit_{camera_id}", "1")
        cam_obj = CamObjList[camera_id] if camera_id in CamObjList else None
        if cam_obj is not None:
            stop_camera(cam_obj)

        # 统计帧率
        pic_count = len(camera_dq_dict[camera_dq_key])
        begin_time = camera_dq_dict[camera_dq_key][0]['host_timestamp']
        end_time = camera_dq_dict[camera_dq_key][-1]['host_timestamp']

        stParam = MVCC_FLOATVALUE()
        memset(byref(stParam), 0, sizeof(MVCC_FLOATVALUE))
        check_result(cam_obj.MV_CC_GetFloatValue, "ResultingFrameRate", stParam)
        print(f'camera{camera_id}原始帧率是：', stParam.fCurValue, '^' * 10)

        if pic_count > 1:
            frame_rate = pic_count / ((end_time - begin_time) / 1000)
            print(f'camera{camera_id}帧率是：', int(frame_rate), '^' * 10, pic_count, ((end_time - begin_time) / 1000))


def camera_init_hk(camera_id, device_object, **kwargs):
    inited = False
    if camera_id in CamObjList:
        inited = True
        CamObj = CamObjList[camera_id]

    if not inited:
        deviceList = MV_CC_DEVICE_INFO_LIST()
        tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE
        check_result(MvCamera.MV_CC_EnumDevices, tlayerType, deviceList)
        CamObj = MvCamera()
        # index 0--->第一个设备
        stDeviceList = cast(deviceList.pDeviceInfo[int(camera_id) - 1], POINTER(MV_CC_DEVICE_INFO)).contents
        check_result(CamObj.MV_CC_CreateHandle, stDeviceList)

        check_result(CamObj.MV_CC_OpenDevice, 5, 0)
        CamObj.MV_CC_CloseDevice()
        # CamObj.MV_CC_DestroyHandle()
        check_result(CamObj.MV_CC_OpenDevice, 5, 0)

    if kwargs.get('feature_test') is True:
        # 功能测试参数设置
        for key in camera_params_feature:
            if isinstance(key[1], bool):
                check_result(CamObj.MV_CC_SetBoolValue, key[0], key[1])
            elif len(key) == 3 and key[2] == 'enum':
                check_result(CamObj.MV_CC_SetEnumValue, key[0], key[1])
            elif isinstance(key[1], int):
                check_result(CamObj.MV_CC_SetIntValue, key[0], key[1])
            elif isinstance(key[1], float):
                check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])
    else:
        # 2022.3.2 5.2柜设置Gamma参数
        if CORAL_TYPE == 5.2:
            CamObj.MV_CC_SetBoolValue("GammaEnable", True)
            CamObj.MV_CC_SetFloatValue("Gamma", 0.7000)
        # 性能测试参数设置
        if kwargs.get("init") is None:
            CamObj.MV_CC_SetEnumValue("ADCBitDepth", 2)
            CamObj.MV_CC_SetEnumValue("PixelFormat", 0x01080009)
            CamObj.MV_CC_SetEnumValue("BalanceWhiteAuto", 0)
            CamObj.MV_CC_SetEnumValue("BalanceRatioSelector", 0)
            CamObj.MV_CC_SetIntValue("BalanceRatio", 1100)
            CamObj.MV_CC_SetEnumValue("BalanceRatioSelector", 1)
            CamObj.MV_CC_SetIntValue("BalanceRatio", 950)
            CamObj.MV_CC_SetEnumValue("BalanceRatioSelector", 2)
            CamObj.MV_CC_SetIntValue("BalanceRatio", 1850)
            for key in camera_params_240:
                if isinstance(key[1], int):
                    check_result(CamObj.MV_CC_SetIntValue, key[0], key[1])
                elif isinstance(key[1], float):
                    check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])
        for key in camera_params_240:
            if kwargs.get(key[0]) is not None:
                check_result(CamObj.MV_CC_SetIntValue, key[0], kwargs.get(key[0]))

    if kwargs.get('high_exposure'):
        if kwargs.get('feature_test') is True:
            for key in high_exposure_params_feature:
                check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])
        else:
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

    # 设置roi 多摄像机暂时不设置
    if not kwargs.get('original') and CORAL_TYPE != 5.3:
        if int(device_object.x1) == int(device_object.x2) == 0:
            pass
        else:
            # 这里的4和16是软件设置的时候，必须是4和16的倍数
            width = (int(device_object.x2) - int(device_object.x1)) - (
                    int(device_object.x2) - int(device_object.x1)) % 16 + 16
            offsetx = int(device_object.x1) - int(device_object.x1) % 16
            height = (int(device_object.y2) - int(device_object.y1)) - (
                    int(device_object.y2) - int(device_object.y1)) % 16 + 16
            offsety = int(device_object.y1) - int(device_object.y1) % 4
            print('设置的roi是：', width, offsetx, height, offsety)
            check_result(CamObj.MV_CC_SetIntValue, 'Width', width)
            check_result(CamObj.MV_CC_SetIntValue, 'Height', height)
            check_result(CamObj.MV_CC_SetIntValue, 'OffsetX', offsetx)
            check_result(CamObj.MV_CC_SetIntValue, 'OffsetY', offsety)

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
            camera_snapshot(dq, data_buf, st_frame_info, cam_obj)
            if temporary is True:
                redis_client.set(f'g_bExit_{camera_id}', 1)
            else:
                time.sleep(0.001)
        else:
            continue


def camera_snapshot(dq, data_buf, stFrameInfo, cam_obj):
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
    dq.append({'image': image,
               'host_timestamp': stFrameInfo.nHostTimeStamp,
               'dev_timestamp_high': stFrameInfo.nDevTimeStampHigh,
               'dev_timestamp_low': stFrameInfo.nDevTimeStampLow,
               'frame_num': stFrameInfo.nFrameNum})
    print('获取到图片了', stFrameInfo.nFrameNum)


def stop_camera(cam_obj):
    cam_obj.MV_CC_StopGrabbing()
    # cam_obj.MV_CC_CloseDevice()
    # cam_obj.MV_CC_DestroyHandle()
    # 目前的柜子类型，只有一个相机，所以销毁所有
    # CamObjList.clear()
    print("stop camera finished..[Debug]")


def check_result(func, *args):
    return_value = func(*args)
    if return_value != 0:
        print("return_value", hex(return_value), *args, func.__name__)
        raise CameraInitFail


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
        camera_ids = []
        for camera_id in HARDWARE_MAPPING_LIST:
            if not camera_id.isdigit():
                continue
            camera_ids.append(camera_id)

        futures = []
        temporary = False if CORAL_TYPE == 5.3 else True
        sync_camera = True if CORAL_TYPE == 5.3 else False
        for camera_id in camera_ids:
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
                                     sync_camera=sync_camera)
            futures.append(future)

        # 默认使用第一个相机中的截图
        if len(camera_ids) == 1 or CORAL_TYPE != 5.3:
            image = None
            for _ in as_completed(futures):
                image = camera_dq_dict.get(self._model.pk + camera_ids[0])[-1]['image']
                if not self.original:
                    image = np.rot90(image, 3)

            try:
                self.src = image
            except UnboundLocalError:
                raise CameraNotResponse
        else:
            # 判断俩个相机都已经进入到了循环中
            while True:
                all_in_loop = True
                for camera_id in camera_ids:
                    if not redis_client.get(f"camera_loop_{camera_id}"):
                        all_in_loop = False
                        break
                if all_in_loop:
                    break
            if sync_camera:
                if self.record_video:
                    timeout = self.record_time
                else:
                    timeout = 0.1
                # 发送同步信号
                with CameraUsbPower(timeout=timeout):
                    pass
            for camera_id in camera_ids:
                redis_client.set(f"g_bExit_{camera_id}", "1")
            for _ in as_completed(futures):
                print('线程结束了')

            # 这里保存的就是同一帧拍摄的所有图片
            frames = collections.defaultdict(list)
            # 同步拍照靠硬件解决，这里获取同步的图片以后，直接拼接即可
            for frame_index in range(min([len(camera_dq_dict.get(self._model.pk + camera_id))
                                          for camera_id in camera_ids])):
                for camera_id in camera_ids:
                    # 在这里进行运算，选出一张图片，赋给self.src
                    src = camera_dq_dict.get(self._model.pk + camera_id).popleft()
                    # 记录来源于哪个相机，方便后续处理
                    src['camera_id'] = camera_id
                    frames[src['frame_num']].append(src)
            # 清空内存
            for camera_id in camera_ids:
                del camera_dq_dict[self._model.pk + camera_id]

            merged_frames = self.get_syn_frame(frames, camera_ids)
            image = merged_frames[0]
            if not self.original:
                image = self.get_roi(merged_frames[0])
                image = np.rot90(image)
            self.src = image

            # 写入到文件夹中，测试用
            if self.record_video:
                if os.path.exists('camera'):
                    import shutil
                    shutil.rmtree('camera')
                    os.mkdir('camera')
                else:
                    os.mkdir('camera')
                for index, merged_img in enumerate(merged_frames):
                    cv2.imwrite(f'camera/{index}.png', merged_img)

            # 清理内存
            del merged_frames

        return 0

    def get_roi(self, src):
        if int(self._model.y1) == 0 and int(self._model.y2) == 0 and int(self._model.x1) == 0 and int(
                self._model.x2) == 0:
            return src
        # 只针对多摄像机，多摄像机没有把参数设置到摄像机上，后续有需求可以直接设置到相机的参数上
        return src[int(self._model.y1):int(self._model.y2), int(self._model.x1):int(self._model.x2)]

    # 从多个相机中获取同步的内容
    def get_syn_frame(self, frames_list, camera_ids):
        # 判断是否丢帧
        frame_nums = []
        max_frame_num = 0

        result_frames = []
        for frame_num, frames in frames_list.items():
            if len(frames) != len(camera_ids):
                continue
            frame_nums.append(frame_num)
            max_frame_num = frame_num if frame_num > max_frame_num else max_frame_num

            # 目前只支持拼接俩个相机的数据
            img1 = frames[0]['image']
            img2 = frames[1]['image']

            host_t_1 = frames[0]['host_timestamp']
            host_t_2 = frames[1]['host_timestamp']
            dev_t_1 = (frames[0]['dev_timestamp_high'] << 32) + frames[0]['dev_timestamp_low']
            dev_t_2 = (frames[1]['dev_timestamp_high'] << 32) + frames[1]['dev_timestamp_low']
            print(frame_num, host_t_2 - host_t_1, dev_t_2 - dev_t_1)
            # print('frame_num: ', frame_num, '&' * 10)

            h1, w1 = img1.shape[:2]
            h2, w2 = img2.shape[:2]

            h = self.get_homography(img1, img2)

            pts1 = np.float32([[0, 0], [0, h1], [w1, h1], [w1, 0]]).reshape(-1, 1, 2)
            pts2 = np.float32([[0, 0], [0, h2], [w2, h2], [w2, 0]]).reshape(-1, 1, 2)
            pts2_ = cv2.perspectiveTransform(pts2, h)
            pts = np.concatenate((pts1, pts2_), axis=0)
            [xmin, ymin] = np.int32(pts.min(axis=0).ravel() - 0.5)
            [xmax, ymax] = np.int32(pts.max(axis=0).ravel() + 0.5)
            t = [-xmin, -ymin]
            ht = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]])

            result = cv2.warpPerspective(img2, ht.dot(h), (xmax - xmin, ymax - ymin))

            result_copy = np.array(result)
            result[t[1]:h1 + t[1], t[0]:w1 + t[0]] = img1

            rows = int(pts2_.max(axis=0).ravel()[1] - pts2_.min(axis=0).ravel()[1])
            cols = int(pts2_.max(axis=0).ravel()[0] - pts2_.min(axis=0).ravel()[0])

            for r in range(t[1], rows):
                weight = (r - t[1]) / (rows - t[1])
                result[r, t[0]: cols, :] = result_copy[r, t[0]: cols, :] * (1 - weight) + img1[r - t[1], 0: cols - t[0], :] * weight
            result_frames.append(result)
            # 记录一下拼接以后的图片大小，后边计算的时候需要用到，只在第一次拼接的时候写入，在重置h矩阵的时候，需要将这个值删除
            merge_shape = get_global_value('merge_shape')
            if merge_shape is None:
                set_global_value('merge_shape', result.shape)
                with open(COORDINATE_CONFIG_FILE, 'at') as f:
                    f.writelines(f'merge_shape={result.shape}\n')

            # 释放内存
            del frames

        lost_frames = set(range(max_frame_num + 1)) - set(frame_nums)
        if lost_frames:
            print('发生了丢帧:', lost_frames, '&' * 10)
        return result_frames

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
        return h

    def move(self, *args, **kwargs):
        if hasattr(self, "src") and args[0]:
            cv2.imwrite(args[0], self.src)
            delattr(self, "src")
            return 0
        elif hasattr(self, "video_src") or self.record_video:
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


if __name__ == '__main__':
    import collections

    FakeDevice = collections.namedtuple("fakeDevice", ["pk", "has_camera"])
    camera_start(1, FakeDevice(0, True))
