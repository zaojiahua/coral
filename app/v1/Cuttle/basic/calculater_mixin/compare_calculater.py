import logging
from collections import Counter

import cv2
import numpy as np
from scipy.cluster.vq import *

from app.execption.outer.error_code.imgtool import IconTooWeek


class FeatureCompareMixin:
    # 之前的代码，合并到一个混入内继续兼容
    def hist(self, refer_im, input_im, threshold):
        # 直方图进行比较的方法，现在没有在用了
        refer_im_hist = self.get_img_hist(refer_im)
        input_im_hist = self.get_img_hist(input_im)
        # d max value is 1(same), min value is 0(different)
        d = cv2.compareHist(refer_im_hist, input_im_hist, cv2.HISTCMP_CORREL)
        self._model.logger.debug(f"hist compare result: {d}")
        if d < threshold:
            return 1
        return 0

    def surf(self, refer_img, input_img, threshold):
        # 判定图标存在的方法  分为两步，第一步用surf分别求两个图的keypoint 和descriptor
        # 第二步是flann取得这些特征点能匹配上的部分，并与阈值做对比  这个方法只看是否存在，不查存在的位置
        kp1, des1 = self.feature_detection_by_surf(refer_img)  # 提取关键点和描述符
        kp2, des2 = self.feature_detection_by_surf(input_img)
        if len(kp1) < 5 or len(kp2) < 5:
            self._model.logger.error("Too few key points are detected on the picture to be compared.")
            return 1
        goodMatch = self.fast_feature_matching_by_flann(des1, des2)
        self._model.logger.debug(f"goodMatch Point num is {len(goodMatch)}")
        if len(goodMatch) < threshold:
            return 1
        return 0

    def numpy_array(self, refer_im, input_im, threshold):
        # 简单的用图片rgb三个通道的均值做比较，暂没有加上方差
        refer_im, input_im = self.image_size_help(refer_im, input_im)
        refer_im_np = refer_im.astype(np.int32)
        input_im_np = input_im.astype(np.int32)
        b, g, r = cv2.split(refer_im_np - input_im_np)
        mean_b = np.mean(np.abs(b))
        mean_g = np.mean(np.abs(g))
        mean_r = np.mean(np.abs(r))
        var_b = np.var(b)
        var_g = np.var(g)
        var_r = np.var(r)
        self._model.logger.debug(
            f"numpy mean_b : {mean_b}; mean_g : {mean_g}; mean_r : {mean_r} ,threshold:{threshold}")
        self._model.logger.debug(f"numpy var_b : {var_b}; var_g : {var_g}; var_r : {var_r}")
        if (mean_b <= threshold) and (mean_g <= threshold) and (mean_r <= threshold):
            return 0
        return 1

    def identify_icon_point(self, input_img, icon_img, height=None, width=None):
        # 有要求小图标不能过小，否则即使能匹配到一些，特征点也太小
        l = self.shape_identify(input_img, icon_img)
        if len(l) < 4:
            self._model.logger.error(f"Too few feature points：{len(l)}")
            raise IconTooWeek
            # return 2010
        self._model.logger.info(f" icon feature number:{len(l)}")
        # 对得到的goodmatch 再进行4分类的聚类，取数目最多的那个类型的位置，就是求得的图标的位置。
        code, centroids = FeatureCompareMixin.kmeans_clustering(l, 4)
        max_centro = Counter(code).most_common(1)[0][0]
        return centroids[max_centro]

    def image_size_help(self, image_1, image_2):
        shape_1 = image_1.shape
        shape_2 = image_2.shape
        if shape_1[0] > shape_2[0]:
            image_1 = cv2.resize(image_1, (shape_2[1], shape_2[0]))
        else:
            image_2 = cv2.resize(image_2, (shape_1[1], shape_1[0]))
        return image_1, image_2

    @classmethod
    def get_img_hist(cls, im):
        # 直方图计算放方法，计算图片的像素直方图分布，这块用的是256/32个bin，三通道分别算
        # im: np_array
        image = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)

        # extract a 3D RGB color histogram from the image,using 8 bins per channel, normalize, and update the index
        img_hist = cv2.calcHist([image], [0, 1, 2], None, [32, 32, 32], [0, 256, 0, 256, 0, 256])
        # 这是做一下归一化
        img_hist = cv2.normalize(img_hist, img_hist).flatten()

        return img_hist

    @classmethod
    def fast_feature_matching_by_flann(cls, des1, des2, thresh=0.5):
        """
        FLANN快速特征匹配
        :param des1: 描述子1
        :param des2: 描述子2
        :param thresh: 阈值
        :return: 匹配结果，列表形式
        """
        # FLANN matcher parameters
        FLANN_INDEX_KDTREE = 0  # 初始化为0
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)  # 创建indexParams索引字典 #kdtrees = 5; 50 checks为合理值
        search_params = dict(checks=50)

        flann = cv2.FlannBasedMatcher(index_params, search_params)  # 初始化flann匹配,为descriptor建立索引树
        matches = flann.knnMatch(np.asarray(des1, np.float32), np.asarray(des2, np.float32),
                                 k=2)  # k值为2，对des1和des2进行knn匹配
        # 准备一个空mask存储goodmatches
        matches_mask = [[0, 0] for i in range(len(matches))]
        good_match = []  # 匹配结果
        for i, (m, n) in enumerate(matches):
            if m.distance < thresh * n.distance:
                matches_mask[i] = [i, 0]
                good_match.append(m)
        return good_match

    @staticmethod
    def feature_detection_by_surf(input_img):
        """
        SURF特征点检测
        :param inputImg: 图片
        :return: 关键点，描述子
        """
        # 这块的几个参数完全决定了surf的得到的key point的个数
        # hessian矩阵阈值主要做限制，特征金字塔的层数个数限制效果，upright为true代表不考虑旋转不变性
        # extended =TRUE 实验中对效果有明显改善，建议后续调整非必要不要去掉
        surf = cv2.xfeatures2d.SURF_create(hessianThreshold=50, nOctaves=4, nOctaveLayers=3, extended=True,
                                           upright=True)  # 初始化surf特征
        kp, des = surf.detectAndCompute(input_img, None)  # 提取关键点和描述符
        if des is None:
            raise IconTooWeek
        return kp, des

    @staticmethod
    def kmeans_clustering(obs, k):
        # 使用kmeans的一个聚类方法，用scipy提供的api
        """
        kmeans聚类算法
        :param obs:待聚合数组
        :param k:阈值
        :return:长度和中心点
        """
        centroids, variance = kmeans2(obs, k)  # variance方差
        code, distance = vq(obs, centroids)  # 矢量量化函数进行归类

        return code, centroids

    def shape_identify(self, input_img, icon_img):
        # 先对refer图标和待识别大图分别进行surf计算，得到特征点和对应的描述符
        kp1, des1 = self.feature_detection_by_surf(input_img)
        kp2, des2 = self.feature_detection_by_surf(icon_img)
        if len(kp1) < 4 or len(kp2) < 4:
            # 特征点小于4个无论能不能匹配上，后面都无法聚类了，所以直接抛异常
            if isinstance(self._model.logger, logging.Logger):
                self._model.logger.error("Too few key points are detected on the picture to be compared.")
            raise IconTooWeek
        # 再对得到特征点进行flann匹配，只留下能匹配的点
        # （一般大图片有很多很多特征点，但小图标特征点比较少，只留下大小图片能匹配的特征点，既大图片上图标的点）
        # 如果大图上没有小图标，这个good_match结果就很小了
        good_match = self.fast_feature_matching_by_flann(des1, des2, 0.5)
        response = self.print_list(kp1, good_match) if good_match else []
        return response

    def print_list(self, kp1, good_match):
        return np.float32([kp1[kpp.queryIdx].pt for kpp in good_match])


def relative2absolute(relative_coordinate, photo_resolution, phone_resolution_height, phone_resolution_width):
    width = relative_coordinate[0] / photo_resolution[1] * phone_resolution_width
    height = relative_coordinate[1] / photo_resolution[0] * phone_resolution_height

    return width, height


def separate_point_pixel(point):
    point_x = point[0]
    point_y = point[1]

    return point_x, point_y
