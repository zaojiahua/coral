import os
import random

import cv2
import numpy as np

from app.v1.Cuttle.basic.common_utli import precise_match, blur_match, check_color_by_position
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageColorSchema, ImageColorRelativePositionSchema
from app.v1.Cuttle.basic.setting import color_rate, color_threshold, strip_str


class ColorMixin(object):
    # 主要负责颜色有关的判断方法的混入

    def is_excepted_color(self, exec_content) -> int:
        # 判断所选区域颜色与设置相同
        data = self._validate(exec_content, ImageColorSchema)
        input_crop = self._crop_image(data.get("input_im"), data.get("areas")[0]).astype(np.int32)
        b_input, g_input, r_input = cv2.split(input_crop)
        r_required, g_required, b_required = data.get("color").split(",")
        result = self._color_judge(b_input, b_required, g_input, g_required, r_input, r_required, data)
        return result

    def is_excepted_color_words(self, exec_content) -> int:
        # 判断所选区域内文字为期待的颜色
        identify_words_list, words_list = self._is_color_words(exec_content)
        return precise_match(identify_words_list, words_list)

    def is_excepted_color_word_blur(self, exec_content) -> int:
        identify_words_list, words_list = self._is_color_words(exec_content)
        return blur_match(identify_words_list, words_list)

    def _is_color_words(self, exec_content):
        data = self._validate(exec_content, ImageColorSchema)
        input_crop = self._crop_image(data.get("input_im"), data.get("areas")[0])
        r, g, b = (int(i) for i in data.get("color").split(","))
        th = (1 - data.get("threshold", 0.99)) * color_threshold
        lower_bgr = np.array([b - th, g - th, r - th])
        upper_bgr = np.array([b + th, g + th, r + th])
        binaryzation = cv2.inRange(input_crop, lower_bgr, upper_bgr)
        words_list = exec_content.get("requiredWords").split(",")
        path = os.path.join(self.kwargs.get("work_path"), f"ocr-{random.random()}.png")
        cv2.imwrite(path, binaryzation)
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip(strip_str) for item in response]
        return identify_words_list, words_list

    def is_excepted_color_in_relative_words_position(self, exec_content):
        # 根据文字+偏移量确定要判断颜色的位置，根据referPic+position确认标准rgb值
        data = self._validate(exec_content, ImageColorRelativePositionSchema)
        input_crop_path = self._crop_image_and_save(data.get("input_im"), data.get("areas")[0])
        src_refer = cv2.imread(data.get("refer_im"))
        position_list = data.get("position").strip().split(' ')
        if float(position_list[1]) <= 1 and float(position_list[0]) <= 1:
            h, w = src_refer.shape[:2]
            position_list = [h * float(position_list[1]), w * float(position_list[0])]
        refer_b, refer_g, refer_r = check_color_by_position(src_refer, int(float(position_list[1])),
                                                            int(float(position_list[0])))
        # input  refer
        with Complex_Center(inputImgFile=input_crop_path, **data, **self.kwargs) as ocr_obj:
            ocr_obj.default_pic_path = input_crop_path
            ocr_obj.get_result()
            x = ocr_obj.cx + ocr_obj.x_shift
            y = ocr_obj.cy + ocr_obj.y_shift
        if type(ocr_obj.result) == int and ocr_obj.result != 0:
            return -2000
        b, g, r = check_color_by_position(cv2.imread(input_crop_path), y, x)
        return self._color_judge(b, refer_b, g, refer_g, r, refer_r, data)

    def _color_judge(self, b_input, b_required, g_input, g_required, r_input, r_required, data):
        # 判断颜色偏差在规定阈值内
        differ_b = np.abs(np.mean(np.abs(b_input)) - int(b_required))
        differ_g = np.abs(np.mean(np.abs(g_input)) - int(g_required))
        differ_r = np.abs(np.mean(np.abs(r_input)) - int(r_required))
        self._model.logger.info(f"differ r g b :{differ_r} {differ_g} {differ_b}")
        result = 0 if (max(differ_b, differ_g, differ_r) - (1 - data.get("threshold", 0.99)) * color_rate) <= 0 else 1
        return result
