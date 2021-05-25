import cv2
import numpy as np

from app.config.setting import CORAL_TYPE
from app.v1.Cuttle.basic.common_utli import threshold_set
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageAreaSchema, ImageOriginalSchema, ImageAreaWithoutInputSchema, \
    ImageRealtimeSchema
from app.v1.Cuttle.basic.setting import icon_threshold, icon_threshold_camera, icon_rate, icon_min_template, \
    icon_min_template_camera


class AreaSelectedMixin(object):
    # 主要负责增加图像选区相关方法

    def has_icon_area_selected(self, exec_content) -> int:
        # 判断所选择区域内有指定图标
        data = self._validate(exec_content, ImageAreaSchema)
        feature_refer = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        image_crop = self._crop_image(data.get("input_im"), data.get("crop_areas")[0])
        feature_point_list = self.shape_identify(image_crop, feature_refer)
        from app.v1.device_common.device_model import Device
        threshold = icon_threshold if Device(pk=self._model.pk).has_camera == False else icon_threshold_camera
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{threshold - (1 - data.get('threshold', 0.99)) * icon_rate}")
        return 0 if len(feature_point_list) >= threshold - (1 - data.get("threshold", 0.99)) * icon_rate else 1

    def smart_ocr_point_crop(self, info_body, match_function="get_result") -> int:
        data = self._validate(info_body, ImageOriginalSchema)
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            from app.v1.device_common.device_model import Device
            dev_obj = Device(pk=self._model.pk)
            h, w = dev_obj.device_height, dev_obj.device_width
            x0, y0 = int(data.get("areas")[0][0] * w), int(data.get("areas")[0][1] * h)
            crop_path = self._crop_image_and_save(ocr_obj.default_pic_path, data.get("areas")[0])
            self.image = ocr_obj.default_pic_path
            ocr_obj._pic_path = crop_path
            getattr(ocr_obj, match_function)()
            ocr_obj.add_bias(x0, y0)
            ocr_obj.point()
        return ocr_obj.result

    def smart_ocr_point_ignore_speed(self, info_body) -> int:
        return self.smart_ocr_point_crop(info_body, match_function="get_result_ignore_speed")

    def smart_icon_point_crop(self, info_body) -> int:
        data = self._validate(info_body, ImageAreaWithoutInputSchema)
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            from app.v1.device_common.device_model import Device
            dev_obj = Device(pk=self._model.pk)
            h, w = dev_obj.device_height, dev_obj.device_width
            x0, y0 = int(data.get("crop_areas")[0][0] * w), int(data.get("crop_areas")[0][1] * h)
            input_crop_path = self._crop_image_and_save(ocr_obj.default_pic_path, data.get("crop_areas")[0])
            self.image = ocr_obj.default_pic_path
            ocr_obj._pic_path = input_crop_path
            ocr_obj.get_result_by_feature(info_body)
            ocr_obj.add_bias(x0, y0)
            ocr_obj.point()
        return ocr_obj.result

    def smart_icon_point_crop_template(self, info_body) -> int:
        data = self._validate(info_body, ImageAreaWithoutInputSchema)
        with Complex_Center(**info_body, **self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            from app.v1.device_common.device_model import Device
            dev_obj = Device(pk=self._model.pk)
            h, w = dev_obj.device_height, dev_obj.device_width
            x0, y0 = int(data.get("crop_areas")[0][0] * w), int(data.get("crop_areas")[0][1] * h)
            input_crop_path = self._crop_image_and_save(ocr_obj.default_pic_path, data.get("crop_areas")[0])
            self.image = ocr_obj.default_pic_path
            ocr_obj._pic_path = input_crop_path
            ocr_obj.get_result_by_template_match(info_body)
            ocr_obj.add_bias(x0, y0)
            ocr_obj.point()
        return ocr_obj.result

    def realtime_picture_compare(self, exec_content) -> int:
        data = self._validate(exec_content, ImageRealtimeSchema)
        input_im_2 = self._crop_image(data.get("input_im_2"), data.get("areas")[0])
        input_im = self._crop_image(data.get("input_im"), data.get("areas")[0])
        return self.numpy_array(input_im, input_im_2, threshold_set(data.get("threshold", 0.99)))

    def has_icon_template_match(self, exec_content) -> int:
        data = self._validate(exec_content, ImageAreaSchema)
        template = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        target = self._crop_image(data.get("input_im"), data.get("crop_areas")[0])
        result = self.template_match(target, template)
        return 0 if result == True else 1

    @staticmethod
    def template_match(target, template):
        result = cv2.matchTemplate(target, template, cv2.TM_SQDIFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        th = icon_min_template if CORAL_TYPE < 5 else icon_min_template_camera
        result = np.abs(min_val) < th
        return result
