from app.v1.Cuttle.basic.calculater_mixin.area_selected_calculater import AreaSelectedMixin
from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.operator.image_operator import ImageHandler
from app.v1.Cuttle.basic.setting import right_switch_percent


class ComplexHandler(ImageHandler, AreaSelectedMixin):

    def smart_ocr_point(self, info_body) -> int:
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            ocr_obj.point()
        return ocr_obj.result

    def smart_icon_point(self, info_body) -> int:
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result_by_feature(info_body)
            ocr_obj.point()
        return ocr_obj.result

    def smart_ocr_long_press(self, info_body) -> int:
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            ocr_obj.long_press()
        return ocr_obj.result

    def smart_icon_long_press(self, info_body) -> int:
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result_by_feature(info_body)
            ocr_obj.long_press()
        return ocr_obj.result

    def smart_ocr_point_extend(self, info_body) -> int:
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            self.image = ocr_obj.default_pic_path
            ocr_obj.get_result()
            from app.v1.device_common.device_model import Device
            device_width = Device(pk=self._model.pk).device_width
            ocr_obj.change_x(device_width * right_switch_percent)
            ocr_obj.point()
        return ocr_obj.result

    def smart_ocr_point_ignore_speed(self, info_body) -> int:
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
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

    # 复合unit输入参数例子：
    # kwargs = {'model': Dummy_model, 'many': False, 'execCmdDict':
    #      {'xyShift': '0 0', 'requiredWords': '蓝牙','functionName': 'smart_ocr_point'},
    #      'work_path': 'D:\\Pacific\\chiron---msm8998---3613ef3d\\1599471222.1818228\\djobwork\\',
    #      'device_label': 'chiron---msm8998---3613ef3d'}
    # info_body = {'xyShift': '0 0', 'requiredWords': '蓝牙'}
