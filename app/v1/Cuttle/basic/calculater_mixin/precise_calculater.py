from app.v1.Cuttle.basic.common_utli import suit_for_blur, blur_match
from app.v1.Cuttle.basic.complex_center import Complex_Center


class PreciseMixin(object):
    # 主要负责精确识别/点击 相关方法的混入
    def has_word_precise(self, exec_content):
        # 命名word少个s，但为了兼容编辑过的用例，短期不能修正
        exec_content, is_blur = suit_for_blur(exec_content)
        required_words_list, path = self.words_prepare(exec_content, "requiredWords")
        # 此处不传递words给ocr service，避免不确定长度文字对结果的限制（会稍微影响速度）
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
            self.extra_result['not_compress_png_list'].append(ocr_obj.get_pic_path())
        identify_words_list = [item.get("text").strip().strip('"[]<>\,.\n') for item in response]
        if is_blur:
            response = blur_match(identify_words_list, required_words_list)
        else:
            response = 0 if set(required_words_list).issubset(set(identify_words_list)) else 1
        return response

    def except_words_precise(self, exec_content) -> int:
        # 判断所选择区域内没有有指定文字
        exec_content, is_blur = suit_for_blur(exec_content)
        words_list, path = self.words_prepare(exec_content, "exceptWords")
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
            self.extra_result['not_compress_png_list'].append(ocr_obj.get_pic_path())
        identify_words_list = [item.get("text").strip('",.\n') for item in response]
        if is_blur:
            for word in words_list:
                for req_word in identify_words_list:
                    if word in req_word:
                        return 1
            return 0
        else:
            return 1 if set(identify_words_list) & set(words_list) else 0
