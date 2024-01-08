import json
import math
import os
import random
import shutil
import traceback

import cv2
import numpy as np

from app.config.ip import OCR_IP, ADB_TYPE
from app.config.setting import CORAL_TYPE
from app.config.url import coral_ocr_url
from app.execption.outer.error_code.imgtool import OcrRetryTooManyTimes, OcrParseFail, OcrWorkPathNotFound, \
    ComplexSnapShotFail, NotFindIcon, OcrShiftWrongFormat
from app.libs.func_tools import handler_switcher
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.common_utli import adb_unit_maker, handler_exec, get_file_name
from app.v1.Cuttle.basic.setting import chinese_ingore, icon_min_template, icon_min_template_camera, \
    light_pyramid_setting, SCREENCAP_CMD, SCREENCAP_CMD_EARLY_VERSION, SCREENCAP_CMD_VERSION_THRESHOLD
from app.v1.eblock.config.setting import BUG_REPORT_TIMEOUT
from app.execption.outer.error_code.djob import ImageIsNoneException


class Complex_Center(object):
    # 2020/09/09 注: 随着复合unit类型增多，数量变大，这个文件已经不适合保持这个名字和相关init方法，待有空余精力需要对此进行处进行重构。
    # 重构时需要注意此处的unit 都需要同时支持 adb无线/机械臂+摄像头/adb有限 三种不同模式。

    # 2021 06/03交接备注
    # 这个模块比较重要，基本上所有的复合unit都通过这个类实现。

    def __init__(self, device_label, requiredWords=None, xyShift="0 0", inputImgFile=None, work_path="", *args,
                 **kwargs):
        # 存很多辅助信息 后边初始化的时候用，所以先设置
        self.kwargs = kwargs
        self.device_label = device_label
        # _pic_path 存实例化时传入的图（很可能没有） 有裁剪区域的时候，裁剪以后的图也是放到这个地方
        self._pic_path = inputImgFile
        # 如果传入的图为正式格式，就往work_path复制一份，用以最后上传至rds 的结果图片
        # if type(inputImgFile) == str and inputImgFile.split(".")[-1].upper() in ["PNG", "JPG", "JPEG", "GIF", "TIF"]:
        #     shutil.copy(inputImgFile, os.path.join(work_path, f"ocr-{str(random.random())[:7]}-InputCopy.png"))
        # ocr 要查找的文字
        self._searching_word = requiredWords
        # 找到文字后的偏移量
        self.x_shift, self.y_shift = self._shift(xyShift)
        # 这个图用来执行时 当场截图存放
        self.default_pic_path = os.path.join(work_path, f"ocr-{str(random.random())[:7]}.png")
        self.work_path = work_path
        self.result = 0
        self.ocr_result = None
        from app.v1.device_common.device_model import Device
        device = Device(pk=device_label)
        # 僚机mode为0，其他除了5型柜也都为0
        self.mode = 0 if (kwargs.get("assist_device_serial_number") is not None or (
                device.has_arm is False and device.has_camera is False)) else 1
        # 3c也是0
        if device.has_arm and device.has_rotate_arm:
            self.mode = 0
        self.logger = setup_logger(f'{device_label}', f'{device_label}.log')
        # 上下裁剪的补偿，用于文字点击时，先裁剪掉上半屏幕（防止同样字干扰），再从结果中加回offset得到真实坐标。
        self.crop_offset = [0, 0, device.device_width, device.device_height]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb:
            if exc_type == OcrRetryTooManyTimes:
                self.logger.warning(f"ocr service retry over 3 times")
                return False
            elif exc_type == OcrParseFail or exc_type == NotFindIcon:
                # 对文字和图标识别抛出的异常，给与结果置为1
                self.logger.warning(f"can not find required words {self._searching_word} in ocr result")
                self.result = 1
                return True
            elif exc_type == NotFindIcon:
                self.logger.warning(f"can not find required icon  in ocr result")
                return True
            elif exc_type == AttributeError:
                traceback.print_exc()
                self.logger.warning(f"find attribute error {exc_val} ")
                self.result = OcrWorkPathNotFound.error_code
                return True
            else:
                return False

    @property
    def ip(self):
        from app.v1.device_common.device_model import Device
        return Device(pk=self.device_label).ip_address

    @property
    def connect_number(self):
        # 是僚机直接用上层传下来的僚机serial number/ip 主机根据1/2345型柜不同选主机ip/serial number
        from app.v1.device_common.device_model import Device
        connect_number = Device(pk=self.device_label).connect_number if self.kwargs.get(
            "assist_device_serial_number") is None else self.kwargs.get("assist_device_serial_number")
        return connect_number

    @staticmethod
    def default_parse_response(result):
        if len(result) == 1 and isinstance(result, list):
            result = result[0]
        return float(result.get("cx")), float(result.get("cy"))

    def get_pic_path(self):
        return self.default_pic_path if self._pic_path is None else self._pic_path

    def get_result(self, parse_function=default_parse_response.__func__):
        # ocr 识别的方法,传递要识别的文字，做精确匹配。
        # ocr请求最多retry3次
        for i in range(3):
            # 如果有文字的话，文字要传递给ocr服务，找文字位置，没有文字的话是识别所有的文字再做判断
            body = {"words": self._searching_word} if self._searching_word else {}
            pic_path = self.get_pic_path()
            # 发送请求给ocr服务
            response = self._ocr_request(**body, pic_path=pic_path)
            if response.get("status") == "success":
                self.logger.info(f"get ocr result {response.get('result')}")
                # 只计算坐标，不return的情况
                if self._searching_word or parse_function.__name__ != self.default_parse_response.__name__:
                    self.ocr_result = response.get('result')
                    pic_x, pic_y = parse_function(response.get("result"))
                    # 把识别得到的x.y结果根据不同的机柜情况-换算到实际需要的坐标
                    rpic_path = self.default_pic_path if self.default_pic_path is not None else self._pic_path
                    self.cal_realy_xy(pic_x, pic_y, rpic_path)
                    self.result = 0
                    break
                # 需要return所有识别出所有文字的结果。
                else:
                    self.result = response.get('result')
                    self.ocr_result = response.get('result')
                    return self.result
            # ocr 找不到对应文字情况，抛异常，会被exit中捕获把结果设置为1
            elif response.get("status") == "not found":
                raise OcrParseFail
            else:
                self.logger.warning(f"ocr fail to get result, response:{response}")
                continue
        else:
            self.logger.error(f"ocr exception : response:{response}")
            raise OcrRetryTooManyTimes(description=f"ocr response:{response}")

    def get_result_ignore_speed(self):
        # 与上面的方法有一些区别，不传递要识别的文字，拿到所有的文字结果，用来做in的判定
        for i in range(3):
            pic_path = self.get_pic_path()
            response = self._ocr_request(pic_path=pic_path)
            if response.get("status") == "success":
                identify_words_list = [
                    (item.get("text").strip().strip('<>[]{}",.\n'), (item.get("cx"), item.get("cy")))
                    for item in response.get('result')]
                self.logger.info(f"get ocr result {response.get('result')}")
                for word, coor_tuple in identify_words_list:
                    if self._searching_word in word:
                        pic_x, pic_y = coor_tuple
                        self.cal_realy_xy(pic_x, pic_y, self.default_pic_path)
                        return
                else:
                    raise OcrParseFail
            elif response.get("status") == "not found":
                raise OcrParseFail
            else:
                self.logger.warning(f"ocr fail to get result, response:{response}")
                continue
        else:
            self.logger.error(f"ocr exception : response:{response}")
            raise OcrRetryTooManyTimes(description=f"ocr response:{response}")

    def cal_realy_xy(self, pic_x, pic_y, input_pic_path):
        from app.v1.device_common.device_model import Device
        device = Device(pk=self.device_label)
        if math.floor(CORAL_TYPE) == 5:
            if self.crop_offset != [0, 0, device.device_width, device.device_height]:
                # 带有摄像头的中文输入，需要先恢复到整张图上的位置
                pic_x = pic_x + self.crop_offset[0]
                pic_y = pic_y + self.crop_offset[1]
            self.cx = pic_x
            self.cy = pic_y
        elif device.has_camera and device.has_arm:
            # 摄像头识别到的文字位置，需要根据手机屏幕与摄像头照片分辨率换算回实际手机上像素位置，带选区的识别需要在具体方法再做选区内坐标到完整图坐标的变换
            if self.crop_offset != [0, 0, device.device_width, device.device_height]:
                # 带有摄像头的中文输入，需要先恢复到整张图上的位置
                pic_x = int(pic_x + int(self.crop_offset[0]))
                pic_y = int(pic_y + int(self.crop_offset[1]))
            src = cv2.imread(input_pic_path)
            # cv2.imwrite("test.png",src)
            pic_h, pic_w = src.shape[:2]
            device_width = device.device_width
            device_height = device.device_height
            self.cx = int(pic_x * (device_width / pic_w))
            self.cy = int(pic_y * (device_height / pic_h))
        elif self.crop_offset != [0, 0, device.device_width, device.device_height]:
            # 截图内裁剪
            self.cx = int(pic_x + int(self.crop_offset[0]))
            self.cy = int(pic_y + int(self.crop_offset[1]))
        else:
            self.cx = int(pic_x)
            self.cy = int(pic_y)

    def add_bias(self, x_bias, y_bias):
        self.cx += x_bias
        self.cy += y_bias

    def set_xy(self, x, y):
        self.cx = x
        self.cy = y

    def change_x(self, value):
        self.cx = value

    def get_result_by_feature(self, info_body, cal_real_xy=True):
        info_body["inputImgFile"] = self.default_pic_path if self._pic_path == None else self._pic_path
        info_body["functionName"] = "identify_icon"
        request_dict = {
            "execCmdDict": info_body,
            "device_label": self.device_label,
            "work_path": os.path.dirname(self.default_pic_path)
        }
        from app.v1.Cuttle.basic.basic_views import UnitFactory
        response = UnitFactory().create("ImageHandler", request_dict)

        if response.get("result") != 0:
            self.result = response.get("result")
            raise NotFindIcon
        point_x, point_y = response["point_x"], response["point_y"]
        if cal_real_xy:
            self.cal_realy_xy(point_x, point_y, self.default_pic_path)
        else:
            self.cx, self.cy = point_x, point_y

    def get_result_by_template_match(self, info_body, cal_real_xy=True):
        target_path = self.default_pic_path if self._pic_path == None else self._pic_path
        target = cv2.imread(target_path)
        template = cv2.imread(info_body.get("referImgFile"))
        with open(info_body.get('configFile'), "r") as json_file_icon:
            json_data_icon = json.load(json_file_icon)
            icon_areas = json_data_icon["area1"]
        h, w = template.shape[:2]
        area = [int(i) if i > 0 else 0 for i in
                [icon_areas[0] * w, icon_areas[1] * h, icon_areas[2] * w, icon_areas[3] * h]]
        template = template[area[1]:area[3], area[0]:area[2]]
        th, tw = template.shape[:2]
        # add light pyramid to support difference of phone-light
        template_list = [np.clip(template * present, 0, 255).astype(np.uint8) for present in
                         light_pyramid_setting] if math.floor(CORAL_TYPE) == 5 else [template]
        for template in template_list:
            result = cv2.matchTemplate(target, template, cv2.TM_SQDIFF_NORMED)
            min_val_original, _, _, _ = cv2.minMaxLoc(result)
            thres = icon_min_template if CORAL_TYPE < 5 else icon_min_template_camera
            if not np.abs(min_val_original) >= thres * 2.5:
                self.logger.info(f"matchTemplate success min value is :{np.abs(min_val_original)}")
                break
        else:
            raise NotFindIcon
        cv2.normalize(result, result, 0, 1, cv2.NORM_MINMAX, -1)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        point_x = min_loc[0] + 1 / 2 * tw
        point_y = min_loc[1] + 1 / 2 * th
        if cal_real_xy:
            self.cal_realy_xy(point_x, point_y, self.default_pic_path)
        else:
            self.cx, self.cy = point_x, point_y

    def _ocr_request(self, **kwargs):
        pic_path = kwargs.get("pic_path")
        if pic_path is None or not os.path.exists(pic_path):
            raise OcrWorkPathNotFound
        # if sys.platform.startswith("win"):
        if self.kwargs.get("ocr_choice") == 2:
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               data=kwargs, ip=f"http://{OCR_IP}:8090")
        else:
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               data=kwargs, ip=f"http://{OCR_IP}:8089")
        return response

    @handler_switcher
    def point(self, **kwargs):
        cmd_list = [f"shell input tap {max(self.cx + self.x_shift, 0)} {max(self.cy + self.y_shift, 0)}"]
        if kwargs.get("ignore_sleep") is not True:
            cmd_list.append("<4ccmd><sleep>0.5")
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number, **self.kwargs)
        if kwargs.get("ignore_arm_reset") is True:
            request_body.update({"ignore_arm_reset": True})
        if kwargs.get('performance_start_point'):
            request_body.update({'performance_start_point': True})
        if kwargs.get('is_init'):
            request_body.update({'is_init': True})
        self.logger.info(
            f"in coral cor ready to point{max(self.cx + self.x_shift, 0)},{max(self.cy + self.y_shift, 0)}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])
    
    @handler_switcher
    def double_click(self, **kwargs):
        cmd_list = [f"double_point{max(self.cx + self.x_shift, 0)} {max(self.cy + self.y_shift, 0)}"]
        if kwargs.get("ignore_sleep") is not True:
            cmd_list.append("<4ccmd><sleep>0.5")
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number, **self.kwargs)
        if kwargs.get("ignore_arm_reset") is True:
            request_body.update({"ignore_arm_reset": True})
        if kwargs.get('performance_start_point'):
            request_body.update({'performance_start_point': True})
        if kwargs.get('is_init'):
            request_body.update({'is_init': True})
        self.logger.info(
            f"in coral cor ready to point{max(self.cx + self.x_shift, 0)},{max(self.cy + self.y_shift, 0)}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])

    @handler_switcher
    def long_press(self, **kwargs):
        cmd_list = [
            f"shell input swipe {self.cx + self.x_shift} {self.cy + self.y_shift} {self.cx + self.x_shift} {self.cy + self.y_shift} 2000"]
        if kwargs.get("ignore_sleep") is not True:
            cmd_list.append("<4ccmd><sleep>1")
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number, **self.kwargs)
        self.logger.info(f"in coral cor ready to long press point{self.cx},{self.cy}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])

    @handler_switcher
    def swipe(self, x_end=None, y_end=None, **kwargs):
        speed = kwargs.get("speed") if isinstance(kwargs.get("speed"), int) else 2000
        x_end = self.cx if x_end is None else x_end
        y_end = self.cy if y_end is None else y_end
        cmd_list = [
            f"shell input swipe {self.cx} {self.cy} {float(x_end)} {float(y_end)} {speed}"]
        if kwargs.get("ignore_sleep") is not True:
            cmd_list.append("<4ccmd><sleep>1")
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number, **self.kwargs)
        self.logger.info(
            f"in coral cor ready to swipe{self.cx, self.cy},{self.cx + float(x_end), self.cy + float(y_end)}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])

    def _shift(self, xyShift):
        try:
            x_shift = float(xyShift.split(" ")[0])
            y_shift = float(xyShift.split(" ")[1])
            if all((-1 < x_shift < 1, -1 < y_shift < 1)):
                from app.v1.device_common.device_model import Device
                dev_obj = Device(pk=self.device_label)

                serial_number = self.kwargs.get("assist_device_serial_number")
                if serial_number is not None:
                    dev_obj = dev_obj.get_subsidiary_device(serial_number=serial_number)

                x_shift = dev_obj.device_width * x_shift
                y_shift = dev_obj.device_height * y_shift

            return (int(x_shift), int(y_shift))
        except Exception as e:
            traceback.print_exc()
            print(repr(e))
            raise OcrShiftWrongFormat

    @handler_switcher
    def snap_shot(self, **kwargs):
        cmd_list = [
            f"{SCREENCAP_CMD} {self.default_pic_path}"
        ]
        from app.v1.device_common.device_model import Device
        device = Device(pk=self.device_label)
        try:
            # 低版本截图指令 这里只能获取到主机的版本号 僚机只能try catch
            if int(device.android_version.split('.')[0]) <= SCREENCAP_CMD_VERSION_THRESHOLD:
                cmd_list = [
                    f"{SCREENCAP_CMD_EARLY_VERSION} {self.default_pic_path}"
                ]
        except Exception:
            pass

        def screencap(cmd_list, device_label, connect_number):
            request_body = adb_unit_maker(cmd_list, device_label, connect_number, **self.kwargs)
            handler_index = 0 if self.mode == 0 else (1 if device.has_camera is True else 0)
            return handler_exec(request_body, kwargs.get("handler")[handler_index])

        try:
            self.result = screencap(cmd_list, self.device_label, self.connect_number)
        # 尝试使用旧的指令获取
        except ImageIsNoneException:
            cmd_list = [
                f"{SCREENCAP_CMD_EARLY_VERSION} {self.default_pic_path}"
            ]
            self.result = screencap(cmd_list, self.device_label, self.connect_number)

        if self.result != 0:
            raise ComplexSnapShotFail(error_code=self.result,
                                      description=str(self.result))
        self.logger.debug("snap-shot in smart ocr finished ")

    @handler_switcher
    def bug_report(self, **kwargs):
        from app.v1.device_common.device_model import Device
        device = Device(pk=self.device_label)
        if not device.has_camera:
            cmd_list = [
                f"bugreport {self.work_path}bugreport.zip"
            ]
            # 传了俩个timeout 改成1个
            self.kwargs['timeout'] = BUG_REPORT_TIMEOUT
            request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number, **self.kwargs)
            handler_exec(request_body, kwargs.get("handler")[0])
            self.logger.debug("bug report finished ")

    def picture_crop(self):
        src = cv2.imread(self.default_pic_path)
        h, w = src.shape[:2]
        self.crop_offset = [0, int(h * chinese_ingore), w, h]
        if self._pic_path is None:
            self._pic_path = get_file_name(self.default_pic_path) + '-wordCrop.png'
        cv2.imwrite(self._pic_path,
                    src[self.crop_offset[1]:self.crop_offset[3], self.crop_offset[0]:self.crop_offset[2]])
        return 0
