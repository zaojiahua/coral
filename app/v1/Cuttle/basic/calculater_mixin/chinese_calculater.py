import pypinyin

from app.execption.outer.error_code.adb import PinyinTransferFail
from app.v1.Cuttle.basic.coral_cor import Complex_Center


class ChineseMixin(object):
    # 主要负责adb输入中文的转换，思路为转换为拼音--换为9宫格坐标--依次点击并找到目标词


    # 九宫格位置
    keyboard_mapping_dict = {
        "abc": (3 / 6, 1 / 6),
        "def": (5 / 6, 1 / 6),
        "ghi": (1 / 6, 3 / 6),
        "jkl": (3 / 6, 3 / 6),
        "mno": (5 / 6, 3 / 6),
        "pqrs": (1 / 6, 5 / 6),
        "tuv": (3 / 6, 5 / 6),
        "wxyz": (5 / 6, 5 / 6)
    }

    def transfer_2_pinyin(self, word):
        return [i[0] for i in pypinyin.pinyin(word, style=pypinyin.NORMAL)]

    def is_chinese(self, word):
        for ch in word:
            if '\u4e00' <= ch <= '\u9fff':
                return True
        return False

    def pinyin_2_coordinate(self, pinyin, device_obj,coor_tuple_list):
        x = device_obj.kx2 - device_obj.kx1
        y = device_obj.ky2 - device_obj.ky1
        for letter in pinyin:
            for key, value in self.keyboard_mapping_dict.items():
                if letter in key:
                    coor_tuple = (device_obj.kx1 + x * value[0], device_obj.ky1 + y * value[1])
                    coor_tuple_list.append(coor_tuple)
                    break
            else:
                raise PinyinTransferFail
        return coor_tuple_list

    def chinese_support(self, words):
        pinyin = self.transfer_2_pinyin(words)
        from app.v1.device_common.device_model import Device
        coor_tuple_list = []
        for pinyin_word in pinyin:
            coor_tuple_list = self.pinyin_2_coordinate(pinyin_word, Device(pk=self._model.pk),coor_tuple_list)
        ocr_choice = {"ocr-server":1}
        ocr_choice.update(self.kwargs)
        with Complex_Center(**ocr_choice, requiredWords=words) as ocr_obj:
            # 先依次敲击9宫格键盘，输入内容
            for coor_tuple in coor_tuple_list:
                ocr_obj.set_xy(*coor_tuple)
                ocr_obj.point()
            # 再通过ocr的方式截图-识别-找到需要输入的词并点击
            ocr_obj.snap_shot()
            ocr_obj.get_result()
            ocr_obj.point()
        return ocr_obj.result


if __name__ == '__main__':
    a = ChineseMixin()
    result = a.transfer_2_pinyin("124")
    print(result)