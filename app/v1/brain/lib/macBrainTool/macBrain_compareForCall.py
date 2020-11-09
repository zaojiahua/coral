import cv2
import numpy as np
from scipy.cluster.vq import *


def main(input_img, TOItem_img):
    TOItem_im = cv2.imread(TOItem_img, cv2.IMREAD_COLOR)
    input_im = cv2.imread(input_img, cv2.IMREAD_COLOR)
    kp1, des1 = feature_detection_by_sift(TOItem_im)
    kp2, des2 = feature_detection_by_sift(input_im)
    if len(kp1) == 0 or len(kp2) == 0:
        return 1
    good_match = fast_feature_matching_by_flann(des1, des2, 0.7)
    if good_match < 40:
        return 1

    l = printList(input_im, kp1, kp2, good_match)

    code, centroids = kmeansClustering(l, 5)

    i = 0
    j = [0, 0, 0, 0, 0]
    for x in code:
        if x == 0:
            j[0] = j[0] + 1
        elif x == 1:
            j[1] = j[1] + 1
        elif x == 2:
            j[2] = j[2] + 1
        elif x == 3:
            j[3] = j[3] + 1
        else:
            j[4] = j[4] + 1
        i = i + 1

    max_centro = j.index(max(j))

    result = centroids[max_centro]

    x, y = separatePointPixel(result)

    return [x, y]


def feature_detection_by_sift(input_img):
    input_img = cv2.inRange(input_img, np.array([0, 0, 155]), np.array([100, 100, 255]))
    sift = cv2.xfeatures2d.SIFT_create(200, 3, 0.1, 100, 1)
    kp1, des1 = sift.detectAndCompute(input_img, None)
    return kp1, des1


def fast_feature_matching_by_flann(des1, des2, thresh):
    FLANN_INDEX_KDTREE = 0
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)  # 创建indexParams索引字典 #kdtrees = 5; 50 checks为合理值
    search_params = dict(checks=50)  # 50times
    flann = cv2.FlannBasedMatcher(index_params, search_params)  # 初始化flann匹配,为descriptor建立索引树
    matches = flann.knnMatch(des1, des2, k=2)  # k值为2，对des1和des2进行knn匹配
    matches_mask = [[0, 0] for i in range(len(matches))]
    good = []
    for i, (m, n) in enumerate(matches):
        if m.distance < thresh * n.distance:
            matches_mask[i] = [1, 0]
            good.append(m)
    return good


def printList(img1_gray, kp1, kp2, goodMatch):
    h1, w1 = img1_gray.shape[:2]  # 返回矩阵的长宽

    p1 = [kpp.queryIdx for kpp in goodMatch]  # 测试图像的特征点描述符（descriptor）的下标
    p2 = [kpp.trainIdx for kpp in goodMatch]  # 样本图像的特征点描述符的下标
    post1 = np.int32([kp1[pp].pt for pp in p1])
    post2 = np.int32([kp2[pp].pt for pp in p2]) + (w1, 0)

    list0 = {}  # 存储所有匹配点
    list1 = {}

    i = 0
    for (x1, y1), (x2, y2) in zip(post1, post2):
        list0[i] = (float(x1), float(y1))
        list1[i] = (float(x2), float(y2))
        i += 1
    l = list(list0.values())

    return l


def kmeansClustering(obs, k):
    """
    kmeans聚类算法
    :param obs:待聚合数组
    :param k:阈值
    :return:长度和中心点
    """
    centroids, variance = kmeans(obs, k)  # variance方差
    code, distance = vq(obs, centroids)  # 矢量量化函数进行归类

    return code, centroids


def separatePointPixel(point):
    point_x = point[0]
    point_y = point[1]

    return point_x, point_y
