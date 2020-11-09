import numpy as np
import cv2


class IdentifyRedArea4Elec:
    def __init__(self, input_img_file, TOItem, brain_handle_req_obj):
        self.inputImgFile = input_img_file
        self.TOItem = TOItem
        self.brainHandleReqObj = brain_handle_req_obj

    def main(self):
        im = cv2.imread(self.inputImgFile)
        imh, imw = im.shape[:2]
        area = [0, 0, imw, 210]
        img = im[area[1]:area[3], area[0]:area[2]]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_red = np.array([0, 43, 46])
        upper_red = np.array([10, 255, 255])
        # mask -> 1 channel
        mask = cv2.inRange(hsv, lower_red, upper_red)
        # 找区域，计算区域面积，1.面积过滤   2.坐标过
        mask, contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            rect = cv2.minAreaRect(contour)  # 生成最小外接矩形
            box = cv2.boxPoints(rect)
            if ((box[0][0] == box[3][0]) and (box[0][1] == box[1][1]) and (box[1][0] == box[2][0]) and (
                    box[2][1] == box[3][1])) or (
                    (box[0][0] == box[1][0]) and (box[2][0] == box[3][0]) and (box[0][1] == box[3][1]) and (
                    box[1][1] == box[2][1])):
                h = max(rect[1])
                w = min(rect[1])
                if w < 1 or w > 10:
                    continue
                if h > 30 or h < 10:
                    continue
                x, y = rect[0]
                if 10 < y < 70:
                    if 100 < x < (imw * (1 / 3)):
                        return 0
                    elif (imw * (2 / 3)) < x < (imw - 50):
                        return 0
                    else:
                        continue

        return 1
