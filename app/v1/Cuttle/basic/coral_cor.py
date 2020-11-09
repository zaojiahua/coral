import os
import random
import string

import cv2

from app.config.url import coral_ocr_url
from app.execption.outer.error_code.imgtool import OcrRetryTooManyTimes, OcrParseFail, OcrWorkPathNotFound, \
    ComplexSnapShotFail, NotFindIcon, OcrShiftWrongFormat
from app.libs.functools import handler_switcher
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.common_utli import adb_unit_maker, handler_exec
from app.v1.Cuttle.basic.setting import orc_server_ip


class Complex_Center(object):
    # 2020/09/09 注: 随着复合unit类型增多，数量变大，这个文件已经不适合保持这个名字和相关init方法，待有空余精力需要对此进行处进行重构。
    # 重构时需要注意此处的unit 都需要同时支持 adb无线/机械臂+摄像头/adb有限 三种不同模式。

    def __init__(self, device_label, requiredWords=None, xyShift="0 0", inputImgFile=None, work_path="", *args,
                 **kwargs):
        self.device_label = device_label
        self._pic_path = inputImgFile
        self._searching_word = requiredWords
        self.x_shift, self.y_shift = self._shift(xyShift)
        self.default_pic_path = os.path.join(work_path, f"ocr-{str(random.random())[:7]}.png")
        self.result = 0
        from app.v1.device_common.device_model import Device
        device = Device(pk=device_label)
        self.mode = 0 if (device.has_arm is False and device.has_camera is False) else 1
        self.logger = setup_logger(f'coral-ocr', f'coral-ocr.log')
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb:
            if exc_type == OcrRetryTooManyTimes:
                self.logger.warning(f"ocr service retry over 3 times")
                return False
            elif exc_type == OcrParseFail or exc_type == NotFindIcon:
                self.logger.warning(f"can not find required words or feature:{self._searching_word} in ocr result")
                self.result = 1
                return True
            elif exc_type == AttributeError:
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
        from app.v1.device_common.device_model import Device
        ip = Device(pk=self.device_label).ip_address if self.kwargs.get(
            "assist_device_serial_number") is None else self.kwargs.get("assist_device_serial_number")
        return ip + ":5555"

    @staticmethod
    def default_parse_response(result):
        if len(result) == 1 and isinstance(result, list):
            result = result[0]
        return float(result.get("cx")), float(result.get("cy"))

    def get_result(self, parse_function=default_parse_response.__func__):
        for i in range(3):
            body = {"words": self._searching_word} if self._searching_word else {}
            pic_path = self.default_pic_path if self._pic_path == None else self._pic_path
            response = self._ocr_request(**body, pic_path=pic_path)
            if response.get("status") == "success":
                self.logger.info(f"get ocr result {response.get('result')}")
                if self._searching_word or parse_function.__name__ != self.default_parse_response.__name__:
                    pic_x, pic_y = parse_function(response.get("result"))
                    self.cal_realy_xy(pic_x, pic_y, pic_path)
                    break
                else:
                    self.result = response.get('result')
                    return self.result
            elif response.get("status") == "not found":
                raise OcrParseFail
            else:
                self.logger.warning(f"ocr fail to get result, response:{response}")
                continue
        else:
            self.logger.error(f"ocr exception : response:{response}")
            raise OcrRetryTooManyTimes(description=f"ocr response:{response}")

    def get_result_ignore_speed(self):
        for i in range(3):
            pic_path = self.default_pic_path if self._pic_path == None else self._pic_path
            response = self._ocr_request(pic_path=pic_path)
            if response.get("status") == "success":
                identify_words_list = [
                    (item.get("text").strip().strip('<>[]{}",.\n'), (item.get("cx"), item.get("cy")))
                    for item in response.get('result')]
                self.logger.info(f"get ocr result {response.get('result')}")
                for word, coor_tuple in identify_words_list:
                    if self._searching_word in word:
                        pic_x, pic_y = coor_tuple
                        self.cal_realy_xy(pic_x, pic_y, pic_path)
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
        if Device(pk=self.device_label).has_camera:
            # 摄像头识别到的文字位置，需要根据手机屏幕与摄像头照片分辨率换算回实际手机上像素位置
            src = cv2.imread(input_pic_path)
            pic_h, pic_w = src.shape[:2]
            device_width = Device(pk=self.device_label).device_width
            device_height = Device(pk=self.device_label).device_height
            self.cx = pic_x * (device_width / pic_w)
            self.cy = pic_y * (device_height / pic_h)
        else:
            self.cx = pic_x
            self.cy = pic_y

    def add_bias(self, x_bias, y_bias):
        self.cx += x_bias
        self.cy += y_bias

    def set_xy(self, x, y):
        self.cx = x
        self.cy = y

    def change_x(self, value):
        self.cx = value

    def get_result_by_feature(self, info_body):
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
            raise NotFindIcon
        point_x, point_y = response["point_x"], response["point_y"]
        self.cal_realy_xy(point_x, point_y, info_body["inputImgFile"])

    def _ocr_request(self, **kwargs):
        pic_path = kwargs.get("pic_path")
        if pic_path is None or not os.path.exists(pic_path):
            raise OcrWorkPathNotFound
        # if sys.platform.startswith("win"):
        if self.kwargs.get("ocr_choice") == 2:
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               data=kwargs, ip=f"http://{orc_server_ip}:8090")
        else:
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               data=kwargs, ip=f"http://{orc_server_ip}:8089")
        return response

    @handler_switcher
    def point(self, **kwargs):
        cmd_list = [f"shell input tap {self.cx + self.x_shift} {self.cy + self.y_shift}", "<4ccmd><sleep>0.5"]
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number)
        self.logger.info(f"in coral cor ready to point{self.cx+ self.x_shift},{self.cy+ self.y_shift}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])

    @handler_switcher
    def long_press(self, **kwargs):
        cmd_list = [
            f"shell input swipe {self.cx + self.x_shift} {self.cy + self.y_shift} {self.cx + self.x_shift} {self.cy + self.y_shift} 2000",
            "<4ccmd><sleep>1"]
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number)
        self.logger.info(f"in coral cor ready to long press point{self.cx},{self.cy}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])

    @handler_switcher
    def swipe(self, x_end=0, y_end=0, **kwargs):
        cmd_list = [
            f"shell input swipe {self.cx} {self.cy} {self.cx + float(x_end)} {self.cy + float(y_end)}",
            "<4ccmd><sleep>1"]
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number)
        self.logger.info(
            f"in coral cor ready to swipe{self.cx, self.cy},{self.cx + float(x_end), self.cy + float(y_end)}")
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])

    def _shift(self, xyShift):
        try:
            return (int(xyShift.split(" ")[0]), int(xyShift.split(" ")[1]))
        except Exception:
            raise OcrShiftWrongFormat

    @handler_switcher
    def snap_shot(self, **kwargs):
        cmd_list = [
            f"shell rm /sdcard/snap.png",
            f"shell screencap -p /sdcard/snap.png",
            f"pull /sdcard/snap.png {self.default_pic_path}"
        ]
        request_body = adb_unit_maker(cmd_list, self.device_label, self.connect_number)
        self.result = handler_exec(request_body, kwargs.get("handler")[self.mode])
        if self.result != 0:
            raise ComplexSnapShotFail(error_code=self.result,
                                      description=str(self.result))
        self.logger.debug("snap-shot in smart ocr finished ")
