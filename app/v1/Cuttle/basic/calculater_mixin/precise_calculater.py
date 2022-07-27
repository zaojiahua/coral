import math

from app.v1.Cuttle.basic.common_utli import suit_for_blur, condition_judge
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.config.setting import CORAL_TYPE


class PreciseMixin(object):
    # 主要负责精确识别/点击 相关方法的混入
    def has_word_precise(self, exec_content):
        # 命名word少个s，但为了兼容编辑过的用例，短期不能修正
        exec_content, is_blur = suit_for_blur(exec_content)
        required_words_list, path = self.words_prepare(exec_content, "requiredWords")
        # 5型柜解析失败重试三次
        if math.floor(CORAL_TYPE) == 5:
            retry_times = 3
        else:
            retry_times = 1
        while retry_times > 0:
            retry_times -= 1
            # 此处不传递words给ocr service，避免不确定长度文字对结果的限制（会稍微影响速度）
            with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
                self.extra_result['not_compress_png_list'].append(ocr_obj.get_pic_path())
                response = ocr_obj.get_result()
                identify_words_list = [item.get("text").strip().strip('"[]<>\,.\n') for item in response]
                success = condition_judge(is_blur, False, required_words_list, identify_words_list)
                if success:
                    return success

    def except_words_precise(self, exec_content) -> int:
        # 判断所选择区域内没有有指定文字
        exec_content, is_blur = suit_for_blur(exec_content)
        words_list, path = self.words_prepare(exec_content, "exceptWords")
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
            self.extra_result['not_compress_png_list'].append(ocr_obj.get_pic_path())
        identify_words_list = [item.get("text").strip('",.\n') for item in response]
        return condition_judge(is_blur, True, words_list, identify_words_list)
