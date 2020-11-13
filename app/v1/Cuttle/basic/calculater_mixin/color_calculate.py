import os
import  random
import cv2
import numpy as np

from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageColorSchema
from app.v1.Cuttle.basic.setting import color_rate, color_threshold, strip_str


class ColorMixin(object):
    # 主要负责颜色有关的判断方法的混入

    def is_excepted_color(self, exec_content) -> int:
        # 判断所选区域颜色与设置相同
        data = self._validate(exec_content, ImageColorSchema)
        input_crop = self._crop_image(data.get("input_im"), data.get("areas")[0]).astype(np.int32)
        b_input, g_input, r_input = cv2.split(input_crop)
        r_required, g_required, b_required = data.get("color").split(",")
        differ_b = np.mean(np.abs(b_input)) - int(b_required)
        differ_g = np.mean(np.abs(g_input)) - int(g_required)
        differ_r = np.mean(np.abs(r_input)) - int(r_required)
        self._model.logger.info(f"differ r g b :{differ_r} {differ_g} {differ_b}")
        result = 0 if (max(differ_b, differ_g, differ_r) - (1 - data.get("threshold", 0.99)) * color_rate) <= 0 else 1
        return result

    def is_excepted_color_words(self, exec_content) -> int:
        # 判断所选区域内文字为期待的颜色
        data = self._validate(exec_content, ImageColorSchema)
        input_crop = self._crop_image(data.get("input_im"), data.get("areas")[0])
        r, g, b = (int(i) for i in data.get("color").split(","))
        lower_bgr = np.array([b - color_threshold, g - color_threshold, r - color_threshold])
        upper_bgr = np.array([b + color_threshold, g + color_threshold, r + color_threshold])
        binaryzation = cv2.inRange(input_crop, lower_bgr, upper_bgr)
        words_list = exec_content.get("requiredWords").split(",")
        path = os.path.join(self.kwargs.get("work_path"), f"ocr-{random.random()}.png")
        cv2.imwrite(path, binaryzation)
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip(strip_str) for item in response]
        for word in set(words_list):
            for indentify_word in set(identify_words_list):
                if word == indentify_word:
                    break
            else:
                return 1
        return 0