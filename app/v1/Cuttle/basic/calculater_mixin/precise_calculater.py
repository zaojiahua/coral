from app.v1.Cuttle.basic.complex_center import Complex_Center


class PreciseMixin(object):
    # 主要负责精确识别/点击 相关方法的混入

    def has_word_precise(self, exec_content):
        required_words_list, path = self.words_prepare(exec_content, "requiredWords")
        # 此处不传递words给ocr service，避免不确定长度文字对结果的限制（会稍微影响速度）
        with Complex_Center(inputImgFile=path,**self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip('"[]<>\,.\n') for item in response]
        response = 0 if set(required_words_list).issubset(set(identify_words_list)) else 1
        return response

    def except_words_precise(self, exec_content) -> int:
        # 判断所选择区域内没有有指定文字
        words_list, path = self.words_prepare(exec_content, "exceptWords")
        with Complex_Center(inputImgFile=path,**self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip('",.\n') for item in response]
        return 1 if set(identify_words_list) & set(words_list) else 0
