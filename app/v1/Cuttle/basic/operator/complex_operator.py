import datetime
import subprocess
import sys

from app.execption.outer.error_code.imgtool import EndPointWrongFormat, OcrParseFail, SwipeAndFindWordsFail, \
    CannotFindRecentVideoOrImage
from app.v1.Cuttle.basic.calculater_mixin.area_selected_calculater import AreaSelectedMixin
from app.v1.Cuttle.basic.common_utli import judge_pic_same
from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.image_schema import SimpleSchema, SimpleVideoPullSchema
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
        content = SimpleSchema().load(content)
        adb_content = content.get("adbCommand")
        self._model.logger.debug(f"adb input:{adb_content}")
        adb_content = adb_content.replace("grep", "findstr") if sys.platform.startswith("win") else adb_content.replace(
            "findstr", "grep")
        execute_result = self.send_adb_request(adb_content)
        with open(content.get("outputPath"), "w")as f:
            f.write(execute_result)
        self._model.logger.debug(f"adb response:{execute_result}")
        return execute_result

    # 复合unit输入参数例子：
    # kwargs = {'model': Dummy_model, 'many': False, 'execCmdDict':
    #      {'xyShift': '0 0', 'requiredWords': '蓝牙','functionName': 'smart_ocr_point'},
    #      'work_path': 'D:\\Pacific\\chiron---msm8998---3613ef3d\\1599471222.1818228\\djobwork\\',
    #      'device_label': 'chiron---msm8998---3613ef3d'}
    # info_body = {'xyShift': '0 0', 'requiredWords': '蓝牙'}
    def icon_found_with_direction(self, content, click=True):
        # 自动找icon
        from app.v1.device_common.device_model import Device
        device_width = Device(pk=self._model.pk).device_width
        device_height = Device(pk=self._model.pk).device_height
        center_x = int(device_width / 2)
        center_y = int(device_height / 2)
        mapping_dict = {"left": (max((center_x - 400), 0), center_y),
                        "right": (min((center_x + 400), device_width), center_y),
                        "down": (center_x, (min((center_y + 450), device_height))),
                        "up": (center_x, (max((center_y - 450), 0)))}
        for i in range(15):
            with Complex_Center(**content, **self.kwargs) as ocr_obj:
                try:
                    ocr_obj.snap_shot()
                    if hasattr(self, "image") and judge_pic_same(ocr_obj.default_pic_path, self.image):
                        return 1
                    self.image = ocr_obj.default_pic_path
                    ocr_obj.get_result()
                    if click:
                        ocr_obj.point()
                except OcrParseFail:
                    ocr_obj.cx = center_x
                    ocr_obj.cy = center_y
                    x_end, y_end = mapping_dict.get(content.get("direction"), (900, 700))
                    ocr_obj.swipe(x_end=x_end, y_end=y_end, speed=500)
                    continue
            return ocr_obj.result
        else:
            return 1

    def pull_recent_video_or_picture(self, content):
        # 需要接受所有格式的文件pull请求
        from app.v1.device_common.device_model import Device
        connect_number = Device(pk=self._model.pk).connect_number
        logger = Device(pk=self._model.pk).logger
        content = SimpleVideoPullSchema().load(content)
        adb_content = content.get("adbCommand")
        file_name_in_server = content.get("fileName")
        format = file_name_in_server.split(".")[-1]
        execute_result = self.send_adb_request(adb_content)
        resource_list = execute_result.split(" ")
        recent_time = datetime.datetime.now()
        file_list = [f.strip("\r\n") for f in resource_list if f.endswith(format)]
        file_list.sort(key=lambda x: x[3:-4])
        if len(file_list) == 0:
            raise CannotFindRecentVideoOrImage
        file_name = file_list[-1].strip().strip('\t')
        logger.debug(f"recent file: {file_name}")
        name_format = "VID%Y%m%d%H%M%S.mp4" if format == "mp4" else "IMG%Y%m%d%H%M%S.jpg"
        name_format_2 = "Record_%Y-%m-%d-%H-%M-%S.mp4" if format == "mp4" else "Screenshot_%Y-%m-%d-%H-%M-%S-%f.jpg"
        if (recent_time - datetime.datetime.strptime(file_name, name_format) ).seconds > 600:
            raise CannotFindRecentVideoOrImage
        response = self.send_adb_request(
            f"adb -s {connect_number} pull /sdcard/DCIM/Camera/{file_name} {file_name_in_server}")
        return response

    def add_judgements_standard(self):
        pass

    def send_adb_request(self, content):
        sub_proc = subprocess.Popen(content, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        restr = sub_proc.communicate()[0]
        try:
            execute_result = restr.strip().decode("utf-8")
        except UnicodeDecodeError:
            execute_result = restr.strip().decode("gbk")
            print("cmd to exec in adb's result:", content, "decode error happened")
        return execute_result

    def icon_found_with_direction_no_click(self, content):
        return self.icon_found_with_direction(content, click=False)
