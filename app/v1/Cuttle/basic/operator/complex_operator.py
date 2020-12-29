import subprocess
import sys

from app.execption.outer.error_code.imgtool import EndPointWrongFormat
from app.v1.Cuttle.basic.calculater_mixin.area_selected_calculater import AreaSelectedMixin
from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.handler import Standard
from app.v1.Cuttle.basic.operator.image_operator import ImageHandler
from app.v1.Cuttle.basic.setting import right_switch_percent, normal_result


class ComplexHandler(ImageHandler, AdbHandler, AreaSelectedMixin):
    standard_list = [
        Standard("", 1)
    ]


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_list.extend(AdbHandler.process_list)

    def before_execute(self, **kwargs):
        # 默认的前置处理方法，根据functionName找到对应方法
        opt_type = self.exec_content.pop("functionName")
        self.func = getattr(self, opt_type)
        return normal_result

    def smart_ocr_point(self, content) -> int:
        with Complex_Center(**content, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            ocr_obj.point()
        return ocr_obj.result

    def smart_icon_point(self, content) -> int:
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result_by_feature(content)
            ocr_obj.point()
        return ocr_obj.result

    def smart_ocr_long_press(self, content) -> int:
        with Complex_Center(**content, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            ocr_obj.long_press()
        return ocr_obj.result

    def smart_icon_long_press(self, content) -> int:
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result_by_feature(content)
            ocr_obj.long_press()
        return ocr_obj.result

    def smart_ocr_point_extend(self, content) -> int:
        with Complex_Center(**content, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            from app.v1.device_common.device_model import Device
            device_width = Device(pk=self._model.pk).device_width
            ocr_obj.change_x(device_width * right_switch_percent)
            ocr_obj.point()
        return ocr_obj.result

    def smart_ocr_point_ignore_speed(self, content) -> int:
        with Complex_Center(**content, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result_ignore_speed()
            ocr_obj.point()
        return ocr_obj.result

    def initiative_remove_interference(self, *args):
        # 主动清除异常方法，return 2
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            return 2

    def press_and_swipe(self, content) -> int:
        with Complex_Center(**content, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            try:
                x_end, y_end = content.get("endPoint").split(" ")
            except:
                raise EndPointWrongFormat
            ocr_obj.swipe(x_end, y_end, speed=20000, ignore_sleep=True)
        return ocr_obj.result

    def has_adb_response(self, content) -> str:
        # return string类型，通过基类的after execute方法处理可能的异常
        # 此方法在windows下和linux下区别很多，情况需要运行后发现再依次添加
        content = content.get("adbCommand")
        self._model.logger.debug(f"adb input:{content}")
        content = content.replace("grep", "findstr") if sys.platform.startswith("win") else content.replace("findstr",
                                                                                                            "grep")
        sub_proc = subprocess.Popen(content, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        restr = sub_proc.communicate()[0]
        try:
            execute_result = restr.strip().decode("utf-8")
        except UnicodeDecodeError:
            execute_result = restr.strip().decode("gbk")
            print("cmd to exec in adb's result:", content, "decode error happened")
        self._model.logger.debug(f"adb response:{execute_result}")
        return execute_result

    # 复合unit输入参数例子：
    # kwargs = {'model': Dummy_model, 'many': False, 'execCmdDict':
    #      {'xyShift': '0 0', 'requiredWords': '蓝牙','functionName': 'smart_ocr_point'},
    #      'work_path': 'D:\\Pacific\\chiron---msm8998---3613ef3d\\1599471222.1818228\\djobwork\\',
    #      'device_label': 'chiron---msm8998---3613ef3d'}
    # info_body = {'xyShift': '0 0', 'requiredWords': '蓝牙'}
