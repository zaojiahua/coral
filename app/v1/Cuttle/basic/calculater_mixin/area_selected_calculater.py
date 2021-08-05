import os

import cv2
import numpy as np

from app.config.setting import CORAL_TYPE
from app.execption.outer.error_code.imgtool import IconBiggerThanField
from app.v1.Cuttle.basic.common_utli import threshold_set, suit_for_blur
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageAreaSchema, ImageAreaWithoutInputSchema, \
    ImageRealtimeSchema, ImageOnlyConfigCompatible
from app.v1.Cuttle.basic.setting import icon_threshold, icon_threshold_camera, icon_rate, icon_min_template, \
    icon_min_template_camera, blur_signal


class AreaSelectedMixin(object):
    # 主要负责增加图像选区相关方法

    # ---------------------------------------------------图标相关--------------------------------------------------------------

    def has_icon_area_selected(self, exec_content) -> int:
        # 判断所选择区域内有指定图标
        # 确认图标存在-2
        data = self._validate(exec_content, ImageAreaSchema)
        # 按照选区先裁剪参考图片-->裁成icon
        feature_refer = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        # 按照选区裁剪输入图片 -->裁成一个大范围
        image_crop = self._crop_image(data.get("input_im"), data.get("crop_areas")[0])
        # 得到特征点的列表
        file_name = data.get('input_im').split("\\")[-1]
        path = os.path.join(self.kwargs.get("work_path"), f"crop-icon_exist1-{file_name}")
        cv2.imwrite(path, image_crop)
        feature_point_list = self.shape_identify(image_crop, feature_refer)
        from app.v1.device_common.device_model import Device
        # 此处的判定为根据区分1234型柜和5型柜，取不同的标准值
        threshold = icon_threshold if Device(pk=self._model.pk).has_camera == False else icon_threshold_camera
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{threshold - (1 - data.get('threshold', 0.99)) * icon_rate}")
        # 判断找到的特征点数量是否足够
        return 0 if len(feature_point_list) >= threshold - (1 - data.get("threshold", 0.99)) * icon_rate else 1

    def smart_icon_point_crop(self, info_body) -> int:
        # 点击图标-2
        data = self._validate(info_body, ImageAreaWithoutInputSchema)
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            x0, y0 = self.crop_input_picture_record_position(data, ocr_obj, "crop_areas")
            ocr_obj.get_result_by_feature(info_body)
            ocr_obj.add_bias(x0, y0)
            ocr_obj.point()
        return ocr_obj.result

    def smart_icon_point_crop_template(self, info_body) -> int:
        # 点击图标-1
        data = self._validate(info_body, ImageAreaWithoutInputSchema)
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            x0, y0 = self.crop_input_picture_record_position(data, ocr_obj, "crop_areas")
            ocr_obj.get_result_by_template_match(info_body)
            ocr_obj.add_bias(x0, y0)
            ocr_obj.point()
        return ocr_obj.result

    def realtime_picture_compare(self, exec_content) -> int:
        # 截图变化对比
        data = self._validate(exec_content, ImageRealtimeSchema)
        # 两张传入的图，都按同一个areas裁剪，得到两个图的src
        input_im_2 = self._crop_image(data.get("input_im_2"), data.get("areas")[0])
        input_im = self._crop_image(data.get("input_im"), data.get("areas")[0])
        # 直接对比两张图的rgb均值
        return self.numpy_array(input_im, input_im_2, threshold_set(data.get("threshold", 0.99)))

    def has_icon_template_match(self, exec_content) -> int:
        # 确认图标存在-1
        data = self._validate(exec_content, ImageAreaSchema)
        template = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        target = self._crop_image(data.get("input_im"), data.get("crop_areas")[0])
        file_name = data.get('input_im').split("\\")[-1]
        path = os.path.join(self.kwargs.get("work_path"), f"crop-icon_exist2-{file_name}")
        cv2.imwrite(path, target)
        result = self.template_match(target, template)
        return 0 if result == True else 1

    def smart_icon_long_press(self, content) -> int:
        # 长按图标-新增选区，要求支持之前没有选区的unit正常运行
        data = self._validate(content, ImageAreaWithoutInputSchema)
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            x0, y0 = self.crop_input_picture_record_position(data, ocr_obj, "crop_areas")
            ocr_obj.get_result_by_template_match(content)
            ocr_obj.add_bias(x0, y0)
            ocr_obj.long_press()
        return ocr_obj.result

    @staticmethod
    def template_match(target, template):
        # 模板匹配的方法，判定图标存在
        if target.shape[0] < template.shape[0] or target.shape[1] < template.shape[1]:
            print(target.shape,template.shape)
            raise IconBiggerThanField
        result = cv2.matchTemplate(target, template, cv2.TM_SQDIFF_NORMED)
        # 选用 cv2.TM_SQDIFF_NORMED时，只看最小值，min_val/min_loc
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        th = icon_min_template if CORAL_TYPE < 5 else icon_min_template_camera
        result = np.abs(min_val) < th
        print(th,np.abs(min_val))
        return result

    # ----------------------------------------文字相关-----------------------------------------------------
    def crop_input_picture_record_position(self, data, ocr_obj, config_name):
        from app.v1.device_common.device_model import Device
        dev_obj = Device(pk=self._model.pk)
        # 拿到手机的分辨率，用来把选区的左上角相对坐标->绝对坐标，后面用来加在识别结果上（因为识别的图是裁剪过，需要点击的位置是全局的）
        h, w = dev_obj.device_height, dev_obj.device_width
        x0, y0 = int(data.get(config_name)[0][0] * w), int(data.get(config_name)[0][1] * h)
        # 裁剪前面截的图，并保存起来
        crop_path = self._crop_image_and_save(ocr_obj.default_pic_path, data.get(config_name)[0])
        self.image = ocr_obj.default_pic_path
        ocr_obj._pic_path = crop_path
        return x0, y0

    def smart_ocr_point_crop(self, info_body, match_function="get_result") -> int:
        # 点击文字-选区，注：未用到的参数match_function，是为兼容之前用例，不可去掉。
        info_body, is_blur = suit_for_blur(info_body)
        match_function = "get_result" if is_blur == False else "get_result_ignore_speed"
        data = self._validate(info_body, ImageOnlyConfigCompatible)
        # 创建一个复合unit中心对象，
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            # 先截一张图
            ocr_obj.snap_shot()
            x0, y0 = self.crop_input_picture_record_position(data, ocr_obj, "areas")
            # 执行ocr_obj的对应match方法
            getattr(ocr_obj, match_function)()
            # 把前面算的左上点的绝对坐标加到识别坐标上来。
            ocr_obj.add_bias(x0, y0)
            # 做点击动作
            ocr_obj.point()
        return ocr_obj.result

    def smart_ocr_long_press(self, content) -> int:
        info_body, is_blur = suit_for_blur(content)
        match_function = "get_result" if is_blur == False else "get_result_ignore_speed"
        data = self._validate(content, ImageOnlyConfigCompatible)
        with Complex_Center(**content, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            x0, y0 = self.crop_input_picture_record_position(data, ocr_obj, "areas")
            getattr(ocr_obj, match_function)()
            ocr_obj.add_bias(x0, y0)
            ocr_obj.long_press()
        return ocr_obj.result

    # -------------------------------------旧方法，已经重写或移除，但已经编辑过的用例还需要支持，所有移入统一位置，不做更新--------------------------------
    def smart_ocr_point_ignore_speed(self, info_body) -> int:
        return self.smart_ocr_point_crop(info_body, match_function="get_result_ignore_speed")
