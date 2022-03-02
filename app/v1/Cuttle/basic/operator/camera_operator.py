import collections
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
    camera_params_240, CamObjList, camera_params_feature, high_exposure_params, high_exposure_params_feature
from app.execption.outer.error_code.imgtool import CameraNotResponse
from app.config.setting import HARDWARE_MAPPING_LIST
from redis_init import redis_client

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
            response = camera_init_hk(device_object, **kwargs)
            temporary = kwargs.get('temporary', True)
            print("half done  has camera? ", device_object.has_camera, 'temporary:', temporary)
        else:
            # 功能测试相机初始化
            kwargs['feature_test'] = True
            response = camera_init_hk(device_object, **kwargs)
            temporary = True
            print("has camera?", device_object.has_camera)

        if temporary is True:
            @func_set_timeout(timeout=GET_ONE_FRAME_TIMEOUT)
            def _inner_func():
                return camera_start_hk(dq, *response, temporary=temporary)

            _inner_func()
        else:
            camera_start_hk(dq, *response, temporary=temporary)

    except Exception as e:
        print('相机初始化异常：', e)
        raise e
    except func_timeout.exceptions.FunctionTimedOut as e:
        print('获取图片超时了！！！')
        raise e
    finally:
        redis_client.set(f"g_bExit_{camera_id}", "1")


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
            if len(key) == 3 and key[2] == 'enum':
                check_result(CamObj.MV_CC_SetEnumValue, key[0], key[1])
            elif isinstance(key[1], int):
                check_result(CamObj.MV_CC_SetIntValue, key[0], key[1])
            elif isinstance(key[1], float):
                check_result(CamObj.MV_CC_SetFloatValue, key[0], key[1])
    else:
        # 性能测试参数设置
        if kwargs.get("init") is None:
            CamObj.MV_CC_SetIntValue("OffsetY", 0)
            CamObj.MV_CC_SetIntValue("OffsetX", 0)
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

    # 设置roi
    if not kwargs.get('original'):
        if int(device_object.x1) == int(device_object.x2) == 0:
            pass
        else:
            # 这里的4和16是软件设置的时候，必须是4和16的倍数
            width = (int(device_object.x2) - int(device_object.x1)) - (int(device_object.x2) - int(device_object.x1)) % 16 + 16
            offsetx = int(device_object.x1) - int(device_object.x1) % 16
            height = (int(device_object.y2) - int(device_object.y1)) - (int(device_object.y2) - int(device_object.y1)) % 16 + 16
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
    while True:
        if redis_client.get(f"g_bExit_{camera_id}") == "1":
            stop_camera(cam_obj)
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
    print('获取到图片了')


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
        print("return_value", hex(return_value), *args)
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

    def snap_shot(self, *args, **kwargs):
        # 摄像头数量不一样的时候，方案不同
        camera_ids = []
        for camera_id in HARDWARE_MAPPING_LIST:
            if not camera_id.isdigit():
                continue
            camera_ids.append(camera_id)

        futures = []
        for camera_id in camera_ids:
            # 相机正在获取图片的时候 不能再次使用
            if redis_client.get(f"g_bExit_{camera_id}") == "0":
                raise CameraInUse()

            executer = ThreadPoolExecutor()
            temporary = False if len(camera_ids) > 1 and CORAL_TYPE == 5.2 else True
            future = executer.submit(camera_start,
                                     camera_id,
                                     self._model,
                                     high_exposure=self.high_exposure,
                                     original=self.original,
                                     temporary=temporary)
            futures.append(future)

        # 默认使用第一个相机中的截图
        if len(camera_ids) == 1 or CORAL_TYPE != 5.3:
            image = None
            for _ in as_completed(futures):
                image = camera_dq_dict.get(self._model.pk + camera_ids[0])[-1]['image']
                if not self.original:
                    image = self.get_roi(image)
                    image = np.rot90(image, 3)

            try:
                self.src = image
            except UnboundLocalError:
                raise CameraNotResponse
        else:
            # 拼接图像 等待1s 多拍几张图片 方便同步
            time.sleep(1)
            for camera_id in camera_ids:
                redis_client.set(f"g_bExit_{camera_id}", "1")
            for _ in as_completed(futures):
                print('线程结束了')
            print(camera_ids, 'a' * 10)
            for camera_id in camera_ids:
                # 在这里进行运算，选出一张图片，赋给self.src
                for src in camera_dq_dict.get(self._model.pk + camera_id):
                    frame_num = src['frame_num']
                    file_path = f'camera_{camera_id}/{frame_num}.png'
                    print(frame_num)
                    cv2.imwrite(file_path, src['image'])
            # self.get_syn_frame(*[camera_dq_dict.get(self._model.pk + camera_id) for camera_id in camera_ids])

        return 0

    def get_roi(self, src):
        # return src[int(self._model.y1):int(self._model.y2), int(self._model.x1):int(self._model.x2)]
        return src

    # 从多个相机中获取同步的内容，同步的第一帧应该是最晚开始拍摄的第一个相机的第一帧，
    # 其他相机找到和这个相机第一帧同步的帧，后边的每一个帧就是一一对应的关系。同步的最后一帧应该是最早结束拍摄的相机的最后一帧，
    # 其他相机晚于这帧后边的内容不再使用
    def get_syn_frame(self, *frame_lists):
        # 先找到最晚开始拍摄的相机
        min_frame = frame_lists[0][0]
        for i in range(10):
            if i > 0:
                print(frame_lists[1][i]['host_timestamp'] - frame_lists[1][i-1]['host_timestamp'])
            # print(frame_lists[1][i]['dev_timestamp_low'])
            print('----------------')
        # for f_l in frame_lists:
        #     # print(f_l[0]['dev_timestamp_low'])
        #     # print(f_l[0]['frame_num'])
        #     # print(f_l[0][''])
        #     print('-----------------')
            # if f_l[0][''] < min_frame['']:
            #     pass

    def move(self, *args, **kwargs):
        if hasattr(self, "src"):
            cv2.imwrite(args[0], self.src)
            delattr(self, "src")
            return 0
        elif hasattr(self, "video_src"):
            # 视频分析，存储每一帧图片，并记录总数
            start = time.time()
            number = 0
            total_number = len(self.video_src)
            with open(get_file_name(args[0]) + ImageNumberFile, "w") as f:
                f.write(str(total_number))
            for i in range(total_number):
                cv2.imwrite(get_file_name(args[0]) + f"__{number}.png", self.video_src.popleft())
                number += 1
            delattr(self, "video_src")
            print("save image time:", time.time() - start)
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
