import os
import random

import cv2
import numpy as np

from app.v1.Cuttle.basic.common_utli import precise_match, blur_match, check_color_by_position, suit_for_blur
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageColorSchema, ImageColorRelativePositionSchema, ImageColorPostionSchema
from app.v1.Cuttle.basic.setting import color_rate, color_threshold, strip_str


class ColorMixin(object):
    # 主要负责颜色有关的判断方法的混入

    def is_excepted_color(self, exec_content) -> int:
        # 判断所选区域颜色与设置相同
        if exec_content.get('color') is not None:
            data = self._validate(exec_content, ImageColorSchema)
            r_required, g_required, b_required = data.get("color").split(",")
        else:
            data = self._validate(exec_content, ImageColorPostionSchema)
            b_required, g_required, r_required = self.get_color_by_position(data)

        input_crop = self._crop_image(data.get("input_im"), data.get("areas")[0]).astype(np.int32)
        b_input, g_input, r_input = cv2.split(input_crop)
        result = self._color_judge(b_input, b_required, g_input, g_required, r_input, r_required, data)
        return result

    def is_excepted_color_words(self, exec_content) -> int:
        # 判断所选区域内文字为期待的颜色
        exec_content, is_blur = suit_for_blur(exec_content)
        identify_words_list, words_list = self._is_color_words(exec_content)
        if not is_blur:
            return precise_match(identify_words_list, words_list)
        else:
            return blur_match(identify_words_list, words_list)

    def get_color_by_position(self, data):
        src_refer = cv2.imread(data.get("refer_im"))
        position_list = data.get("position").strip().split(' ')
        if float(position_list[1]) <= 1 and float(position_list[0]) <= 1:
            # 位置换为绝对坐标
            h, w = src_refer.shape[:2]
            position_list = [w * float(position_list[0]), h * float(position_list[1])]
        b, g, r = check_color_by_position(src_refer, int(float(position_list[1])), int(float(position_list[0])))
        return b, g, r

    def _is_color_words(self, exec_content):
        # 兼容旧的
        if exec_content.get('color') is not None:
            data = self._validate(exec_content, ImageColorSchema)
            r, g, b = (int(i) for i in data.get("color").split(","))
        else:
            data = self._validate(exec_content, ImageColorPostionSchema)
            b, g, r = self.get_color_by_position(data)

        input_crop = self._crop_image(data.get("input_im"), data.get("areas")[0])
        th = (1 - data.get("threshold", 0.99)) * color_threshold
        lower_bgr = np.array([b - th, g - th, r - th])
        upper_bgr = np.array([b + th, g + th, r + th])
        # 根据rgb的上下限来二值化，超过边界的值会自动截断，既把指定颜色设置白色，其他都变黑
        binaryzation = cv2.inRange(input_crop, lower_bgr, upper_bgr)
        words_list = exec_content.get("requiredWords").split(",")
        path = os.path.join(self.kwargs.get("work_path"), f"ocr-{random.random()}.png")
        cv2.imwrite(path, binaryzation)
        # 拿上面生成的二值化图片去识别问题，除了指定颜色其他都换为黑色了
        # （这儿有一种bug，就是选了白色背底色，其他彩色文字变成黑色之后，黑白依旧可以看出来）
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip(strip_str) for item in response]
        return identify_words_list, words_list

    def is_excepted_color_in_relative_words_position(self, exec_content):
        # 根据文字+偏移量确定要判断颜色的位置，根据referPic+position确认标准rgb值
        data = self._validate(exec_content, ImageColorRelativePositionSchema)
        input_crop_path = self._crop_image_and_save(data.get("input_im"), data.get("areas")[0])
        refer_b, refer_g, refer_r = self.get_color_by_position(data)

        # input  refer
        info_body, is_blur = suit_for_blur(data)
        match_function = "get_result" if is_blur == False else "get_result_ignore_speed"
        with Complex_Center(inputImgFile=input_crop_path, **data, **self.kwargs) as ocr_obj:
            ocr_obj.default_pic_path = input_crop_path
            getattr(ocr_obj, match_function)()
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

    # ------------------------------已经废弃的unit   但还需要支持之前用过的job  不能删除----------------------
    def is_excepted_color_word_blur(self, exec_content) -> int:
        identify_words_list, words_list = self._is_color_words(exec_content)
        return blur_match(identify_words_list, words_list)
