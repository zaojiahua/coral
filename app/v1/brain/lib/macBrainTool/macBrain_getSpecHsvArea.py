import cv2, pytesseract
import numpy as np


def get_spec_hsv_area(input_img, lower_hsv, upper_hsv):
    # read image
    img = cv2.imread(input_img)
    kernel_4 = np.ones((4, 4), np.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = np.array(lower_hsv)
    upper = np.array(upper_hsv)
    mask = cv2.inRange(hsv, lower, upper)
    # 卷积滤波
    erosion = cv2.erode(mask, kernel_4, iterations=1)  # 腐蚀
    erosion = cv2.erode(erosion, kernel_4, iterations=1)
    dilation = cv2.dilate(erosion, kernel_4, iterations=1)  # 膨胀
    target = cv2.bitwise_and(img, img, mask=dilation)
    # 二值图
    ret, binary = cv2.threshold(dilation, 127, 255, cv2.THRESH_BINARY)
    image, contours, hierarchy = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    i = 1
    area_point_data_dict = {}
    area_list = []
    max_area = []
    for contour in contours:
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        box = np.int0(box)
        area = int(rect[1][1]) * int(rect[1][0])
        rect_area_dicts = {}
        point_data_dict = {"LowerLeft": [int(box[0][0]), int(box[0][1])], "UpperLeft": [int(box[1][0]), int(box[1][1])],
                           "UpperRight": [int(box[2][0]), int(box[2][1])],
                           "LowerRight": [int(box[3][0]), int(box[3][1])]}
        rect_area_dicts[area] = point_data_dict
        area_point_data_dict.update(rect_area_dicts)
        for area in rect_area_dicts:
            area_list.append(area)
        max_area = area_list[area_list.index(max(area_list))]
    point_data_dict = area_point_data_dict[max_area]
    orig_heigth = np.hypot(point_data_dict["LowerLeft"][0] - point_data_dict["UpperLeft"][0],
                           point_data_dict["LowerLeft"][1] - point_data_dict["UpperLeft"][1])
    orig_width = np.hypot(point_data_dict["LowerRight"][0] - point_data_dict["LowerLeft"][0],
                          point_data_dict["LowerRight"][1] - point_data_dict["LowerLeft"][1])
    lower_left_point = point_data_dict["LowerLeft"]
    upper_left_point = point_data_dict["UpperLeft"]
    upper_right_point = point_data_dict["UpperRight"]
    lower_right_point = point_data_dict["LowerRight"]
    pts1 = np.float32([upper_right_point, lower_right_point, upper_left_point, lower_left_point])
    pts2 = np.float32([[0, 0], [orig_heigth, 0], [0, orig_width], [orig_heigth, orig_width]])
    m = cv2.getPerspectiveTransform(pts1, pts2)
    ret_image_object = cv2.warpPerspective(img, m, (int(orig_heigth), int(orig_width)))
    tmp_string = pytesseract.image_to_string(ret_image_object, lang='chi_sim')
    ret_string = "".join(list(filter(str.isalnum, tmp_string)))
    return ret_string
