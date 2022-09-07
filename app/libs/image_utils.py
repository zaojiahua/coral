import cv2
import numpy as np


# 获取图像变换的H矩阵
def get_homography(img1, img2):
    sift = cv2.xfeatures2d.SIFT_create()
    kp1_origin, des1 = sift.detectAndCompute(img1, None)
    kp2_origin, des2 = sift.detectAndCompute(img2, None)
    kp1 = np.float32([kp.pt for kp in kp1_origin])
    kp2 = np.float32([kp.pt for kp in kp2_origin])

    bf = cv2.BFMatcher()
    matches = bf.knnMatch(des1, des2, k=2)
    goods = []

    # 调试的时候打开，看特征点匹配的怎么样
    # for m, n in matches:
    #     if m.distance < 0.3 * n.distance:
    #         goods.append([m])
    # result = cv2.drawMatchesKnn(img1, kp1_origin, img2, kp2_origin, goods[:10], None, flags=2)
    # cv2.imwrite('camera/matches.png', result)
    # goods = []

    for m in matches:
        if len(m) == 2 and m[0].distance < 0.3 * m[1].distance:
            goods.append((m[0].queryIdx, m[0].trainIdx))

    if len(goods) > 4:
        ptsA = np.float32([kp1[i] for i, _ in goods])
        ptsB = np.float32([kp2[i] for _, i in goods])

        (H, status) = cv2.findHomography(ptsA, ptsB, cv2.RANSAC, 4.0)
        print(H)
        del img1, img2
        return H
