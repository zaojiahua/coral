import os
import random

import cv2
import numpy as np

from app.execption.outer.error_code.imgtool import OcrParseFail, RecordWordsFindNoWords, \
    IconTooWeek
from app.v1.Cuttle.basic.calculater_mixin.area_selected_calculater import AreaSelectedMixin
from app.v1.Cuttle.basic.calculater_mixin.color_calculate import ColorMixin
from app.v1.Cuttle.basic.calculater_mixin.compare_calculater import FeatureCompareMixin
from app.v1.Cuttle.basic.calculater_mixin.perforamnce_calculater import PerformanceMinix
from app.v1.Cuttle.basic.calculater_mixin.precise_calculater import PreciseMixin
from app.v1.Cuttle.basic.calculater_mixin.test_calculater import TestMixin
from app.v1.Cuttle.basic.common_utli import threshold_set
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageSchema, ImageBasicSchema, ImageBasicSchemaCompatible, \
    ImageSchemaCompatible
from app.v1.Cuttle.basic.operator.handler import Handler, Abnormal
from app.v1.Cuttle.basic.setting import bounced_words, icon_threshold, icon_threshold_camera, icon_rate

VideoSearchPosition = 0.5


class ImageHandler(Handler, FeatureCompareMixin, PreciseMixin, AreaSelectedMixin, ColorMixin, PerformanceMinix,
                   TestMixin):
    _error_dict = {
        "configFile": -22,
        "inputImgFile": -23,
        "referImgFile": -24,
        "identifyIconFail": -25,
        "configArea": -26,
        "fileName": -27,
        "position": -28,
        "color": -29,
        "inputImgFile2": -30,
        "percent": -31

    }
    # mark 为int 因为img func 返回int
    process_list = [Abnormal(mark=1, method="clear", code=1),
                    Abnormal(mark=2, method="clear", code=0)]

    skip_list = ["realtime_picture_compare", "end_point_with_fps_lost"]

    def img_compare_func3(self, exec_content, **kwargs) -> int:
        # 图像对比，均值方差对比方法，现在基本不在用了。
        data = self._validate(exec_content, ImageSchemaCompatible)
        for area in data.get("areas"):
            result = self.numpy_array(self._crop_image(data.get("refer_im"), area),
                                      self._crop_image(self.image, area),
                                      threshold_set(data.get("threshold", 0.99)))
            if result != 0:
                return result
        return 0

    def identify_icon(self, exec_content, is_write_file=True) -> int:
        # surf特征找图标方法，返回位置，现在基本不在用了 （返回类型特殊）
        data = self._validate(exec_content, ImageSchema)
        try:
            result = self.identify_icon_point(self._crop_image(data.get("input_im"), [1, 1, 1, 1]),
                                              self._crop_image(data.get("refer_im"), data.get("areas")[0]))
        except IconTooWeek:
            return IconTooWeek.error_code
        point_x = result[0]
        point_y = result[1]
        self._model.logger.debug(f"icon position in picture:{point_x},{point_y}")
        if data.get("output_path"):
            self._write_down(data.get("output_path"), f"{round(point_x, 2)} {round(point_y, 2)}")
        # extra_result 的结果会最终合并到unit的结果中去
        self.extra_result = {"point_x": float(point_x), "point_y": float(point_y)}
        return 0

    def identify_icon_template(self, exec_content):
        data = self._validate(exec_content, ImageSchema)

        template = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        target = cv2.imread(data.get("input_im"))
        th, tw = template.shape[:2]
        result = cv2.matchTemplate(target, template, cv2.TM_SQDIFF_NORMED)
        cv2.normalize(result, result, 0, 1, cv2.NORM_MINMAX, -1)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        point_x = min_loc[0] + 1 / 2 * tw
        point_y = min_loc[1] + 1 / 2 * th
        self._model.logger.debug(f"icon position in picture:{point_x},{point_y}")
        if data.get("output_path"):
            self._write_down(data.get("output_path"), f"{round(point_x, 2)} {round(point_y, 2)}")
        # extra_result 的结果会最终合并到unit的结果中去
        self.extra_result = {"point_x": float(point_x), "point_y": float(point_y)}
        return 0

    def has_icon(self, exec_content) -> int:
        # 判断所选择区域内有指定图标
        data = self._validate(exec_content, ImageSchema)
        feature_refer = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        try:
            feature_point_list = self.shape_identify(cv2.imread(data.get("input_im")), feature_refer)
        except IconTooWeek:
            return IconTooWeek.error_code
        from app.v1.device_common.device_model import Device
        threshold = icon_threshold if Device(pk=self._model.pk).has_camera == False else icon_threshold_camera
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{threshold - (1 - data.get('threshold', 0.99)) * icon_rate}")
        return 0 if len(feature_point_list) >= threshold - (1 - data.get("threshold", 0.99)) * icon_rate else 1

    def words_prepare(self, exec_content, key):
        data = self._validate(exec_content, schema=ImageBasicSchemaCompatible)
        words_list = exec_content.get(key).split(",")
        input = self._crop_image(self.image, data.get("areas")[0])
        path = os.path.join(self.kwargs.get("work_path"), f"ocr-{random.random()}.png")
        cv2.imwrite(path, input)
        return words_list, path

    def record_words(self, exec_content) -> int:
        data = self._validate(exec_content, ImageSchemaCompatible)
        path = self._crop_image_and_save(data.get("input_im"), data.get("areas")[0])
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            self.image = path
            result = ocr_obj.get_result()
            if not isinstance(result, list) or len(result) == 0:
                raise RecordWordsFindNoWords
            words = result[0].get("text")
            self._write_down(data.get("output_path"), f"{words}")
        return 0

    def clear(self, *args):
        if not hasattr(self,"image") or self.image is None:
            return 1
        with Complex_Center(inputImgFile=self.image, **self.kwargs) as ocr_obj:
            ocr_obj.get_result(parse_function=self._parse_function)
            if ocr_obj.result == 0:
                ocr_obj.point()
                return 0
            return ocr_obj.result

    #   -------------辅助函数---------
    def _validate(self, exec_content, schema):
        data = schema().load(exec_content)
        self.image = data.get("input_im", "")
        return data

    @staticmethod
    def _parse_function(result_list):
        for i in result_list:
            for word in bounced_words:
                if word == i.get("text"):
                    return float(i.get("cx")), float(i.get("cy"))
        else:
            raise OcrParseFail

    def _crop_image(self, image_path, area):
        # 常用方法，根据area裁剪输入路径下的图片，并返回图片内容矩阵
        try:
            image = cv2.imread(image_path)
            if area[3] == area[2] == 0.99999 and area[0] == area[0] == 0:
                return image
            if any(np.array(area) < 1):
                h, w = image.shape[:2]
                area = [int(i) if i > 0 else 0 for i in [area[0] * w, area[1] * h, area[2] * w, area[3] * h]]
            elif all(np.array(area) == 1):
                return image
            return image[area[1]:area[3], area[0]:area[2]]
        except TypeError as e:
            return None

    def _crop_image_and_save(self, image_path, area, mark=''):
        # 在上一个方法的基础上，把结果保存到返回的路径中去
        src = self._crop_image(image_path, area)
        if src is not None:
            new_path = ".".join(image_path.split(".")[:-1]) + mark + "-crop.jpg"
            cv2.imwrite(new_path, src)
            return new_path

    def _write_down(self, file, context):
        fp = open(file, 'w')
        fp.write(context)
        fp.close()
        return 0

    #   ------------------------------已经废弃的unit ，但不能删除-------------------------

    def has_words(self, exec_content) -> int:
        # 判断所选择区域内有指定文字
        words_list, path = self.words_prepare(exec_content, "requiredWords")
        # 此处不传递words给ocr service，避免不确定长度文字对结果的限制（会稍微影响速度）
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip('",.\n') for item in response]
        for word in set(words_list):
            for indentify_word in set(identify_words_list):
                if word in indentify_word:
                    break
            else:
                return 1
        return 0

    def except_words(self, exec_content) -> int:
        # 判断所选择区域内没有有指定文字
        words_list, path = self.words_prepare(exec_content, "exceptWords")
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip('",.\n') for item in response]
        for word in set(words_list):
            for indentify_word in set(identify_words_list):
                if word in indentify_word:
                    return 1
        return 0

    def is_pure(self, exec_content):
        # 规划一半未启用的方法，暂时无用
        data = self._validate(exec_content, ImageBasicSchema)
        feature_refer = self._crop_image(data.get("refer_im"), data.get("areas")[0])

    def words_judegment(self, words: str, identify_words_list: list):
        #
        if "^" in words:
            required_words_list = words.split("^")
            for word in identify_words_list:
                if word in required_words_list:
                    return True
            return False
        else:
            required_words_list = words.split("&")
            for word in required_words_list:
                if word not in identify_words_list:
                    return False
            return True
