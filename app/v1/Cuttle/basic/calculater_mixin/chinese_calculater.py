import datetime
import time

import pypinyin
import cv2
import numpy as np

from app.config.setting import CORAL_TYPE
from app.execption.outer.error_code.adb import PinyinTransferFail
from app.v1.Cuttle.basic.complex_center import Complex_Center


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
        # 把文字转换成拼音的列表
        return [i[0] for i in pypinyin.pinyin(word, style=pypinyin.NORMAL)]

    def is_chinese(self, word):
        # 判定文字是中文
        for ch in word:
            if '\u4e00' <= ch <= '\u9fff':
                return True
        return False

    @staticmethod
    def keyboard_pos_dict(img):
        # 将图片保存下来，方便以后做优化
        now = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        cv2.imwrite(f'/app/source/{now}.png', img)
        # 取一半以下的区域进行判断
        h, w, _ = img.shape

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        ret, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)

        # 通过sobel算子，获取高频部分
        sobel_x = cv2.Scharr(binary, cv2.CV_64F, 1, 0)
        sobel_x = cv2.convertScaleAbs(sobel_x)
        sobel_y = cv2.Scharr(binary, cv2.CV_64F, 0, 1)
        sobel_y = cv2.convertScaleAbs(sobel_y)
        sobel = cv2.addWeighted(sobel_x, 0.5, sobel_y, 0.5, 5)

        # 通过腐蚀和膨胀使得文字部分成为一块一块的区域，方便获取轮廓
        element1 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        element2 = cv2.getStructuringElement(cv2.MORPH_RECT, (23, 23))
        dilation = cv2.dilate(sobel, element2, iterations=1)
        erosion = cv2.erode(dilation, element1, iterations=1)
        # dilation = cv2.dilate(erosion, element2, iterations=1)

        # 获取轮廓之前，需要先是二值图像
        ret, binary = cv2.threshold(erosion, 100, 255, cv2.THRESH_BINARY)

        _, contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        target_contours = []
        # 查找符合条件的轮廓
        for contour_index, contour_points in enumerate(contours):
            # 遍历组成轮廓的每个坐标点
            next_contour = False
            for point in contour_points:
                if point[0][1] < h / 2 or point[0][1] > h * 0.9:
                    next_contour = True
                    break
            if next_contour:
                continue

            m = cv2.moments(contour_points)
            # 获取对象的质心
            cx = int(m['m10'] / m['m00'])
            cy = int(m['m01'] / m['m00'])
            target_contours.append(np.array([[int(cx), int(cy)]]))

        # 查找位于中心线上的三个点
        three_point = []
        for contour_points in target_contours:
            if abs(contour_points[0][0] - w / 2) < 10:
                three_point.append(contour_points)
                # cv2.putText(img, '1', contour_points[0], cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 0), 2)
        # 直接使用最上面的三个
        origin_three_point = sorted(three_point, key=lambda x: x[0][1])

        # 查找和3个点位于同一水平面的点，然后从这些点中找俩个距离最近且距离几乎相等的点，这样就把查找和验证放到一块了
        THREE_POINT = 3
        for i in range(len(origin_three_point)):
            if i + THREE_POINT > len(origin_three_point):
                break
            three_point = origin_three_point[i:i + THREE_POINT]

            result_contours = []
            for point in three_point:
                point_level = []
                for contour_points in target_contours:
                    if abs(point[0][1] - contour_points[0][1]) < 10:
                        point_level.append((contour_points, np.sqrt(np.sum((point[0] - contour_points[0]) ** 2))))
                        # cv2.putText(img, '1', contour_points[0], cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 0), 2)
                if len(point_level) >= THREE_POINT:
                    point_level = sorted(point_level, key=lambda x: x[1])
                    # 第一个点是point本身
                    if abs(point_level[1][1] - point_level[2][1]) < 10:
                        point_level = point_level[:THREE_POINT]
                        order_point = sorted(point_level, key=lambda x: x[0][0][0])
                        # print(order_point)
                        result_contours += order_point

            if len(result_contours) == THREE_POINT * 3:
                distance = [point[1] for point in result_contours if point[1] != 0]
                min_val, max_val = min(distance), max(distance)
                # 几对点距离相差太大，代表y的位置不对
                if max_val - min_val > 20:
                    continue

                result_contours = [point[0] for point in result_contours]
                # 画出轮廓，方便测试
                # img = cv2.drawContours(img, result_contours, -1, (0, 255, 0), 30)
                return result_contours

    def pinyin_2_coordinate(self, pinyin, device_obj, coor_tuple_list, keyboard_pos=None):
        # 把拼音转换成9宫格上的位置。
        x = device_obj.kx2 - device_obj.kx1
        y = device_obj.ky2 - device_obj.ky1
        # 遍历每个拼音字母
        for letter in pinyin:
            # 对每个字母遍历9宫格9个位置，找到对应位置，并得出字母的坐标
            for key_index, key in enumerate(self.keyboard_mapping_dict.keys()):
                if letter in key:
                    if keyboard_pos:
                        coor_tuple_list.append(keyboard_pos[key_index + 1][0])
                        break
                    else:
                        value = self.keyboard_mapping_dict[key]
                        coor_tuple = (device_obj.kx1 + x * value[0], device_obj.ky1 + y * value[1])
                        coor_tuple_list.append(coor_tuple)
                        break
            else:
                raise PinyinTransferFail
        return coor_tuple_list

    def chinese_support(self, words):
        pinyin = self.transfer_2_pinyin(words)

        from app.v1.device_common.device_model import Device
        dev_obj = Device(pk=self._model.pk)
        serial_number = self.kwargs.get("assist_device_serial_number")
        if serial_number is not None:
            dev_obj = dev_obj.get_subsidiary_device(serial_number=serial_number)

        ocr_choice = {"ocr-server": 1}
        ocr_choice.update(self.kwargs)
        with Complex_Center(**ocr_choice, requiredWords=words) as ocr_obj:
            # 先截图一张，用来获取坐标位置
            ocr_obj.snap_shot()
            keyboard_pos = self.keyboard_pos_dict(cv2.imread(ocr_obj.get_pic_path()))
            # 保存图片，方便后续优化
            if not keyboard_pos:
                self.extra_result['not_compress_png_list'].append(ocr_obj.get_pic_path())
            self._model.logger.debug(f'获取到的键盘坐标是：{keyboard_pos}')

            coor_tuple_list = []
            for pinyin_word in pinyin:
                coor_tuple_list = self.pinyin_2_coordinate(pinyin_word, dev_obj, coor_tuple_list, keyboard_pos)

            # 先依次敲击9宫格键盘，输入内容
            for index, coor_tuple in enumerate(coor_tuple_list):
                ocr_obj.set_xy(*coor_tuple)
                if index == len(coor_tuple_list) - 1:
                    # 在最后一个键盘敲后回到初始位置
                    ocr_obj.point(ignore_sleep=True)
                else:
                    # 敲击过程中每次敲击后不回位
                    ocr_obj.point(ignore_sleep=True, ignore_arm_reset=True)

            # 再通过ocr的方式截图-识别-找到需要输入的词并点击
            if CORAL_TYPE >= 5: # 5型柜拿照片速度太快，要等待1.5秒至机械臂撤回等待位，避免遮挡点击出的文字
                time.sleep(1.5)

            ocr_obj.snap_shot()
            ocr_obj.picture_crop()
            # 最后验证的ocr不压缩
            self.extra_result['not_compress_png_list'].append(ocr_obj.get_pic_path())
            ocr_obj.get_result()
            ocr_obj.point()
        return ocr_obj.result


if __name__ == '__main__':
    a = ChineseMixin()
    result = a.transfer_2_pinyin("124")
    print(result)
