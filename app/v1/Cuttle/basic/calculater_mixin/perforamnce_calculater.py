import os
import time
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.common_utli import judge_pic_same
from app.v1.Cuttle.basic.image_schema import PerformanceSchema
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax
from app.v1.Cuttle.basic.performance_center import PerformanceCenter
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_rate


class PerformanceMinix(object):
    dq = deque(maxlen=CameraMax)

    def start_point_with_icon(self, exec_content):
        performance = self.test_performance(exec_content)
        return performance.start_loop(self._icon_find)

    def start_point_with_point(self, exec_content):
        # 先异步去执行操作，再计算起始点。
        executer = ThreadPoolExecutor()
        exec_task = executer.submit(self.test_performance_with_point, exec_content).add_done_callback(executor_callback)
        time.sleep(0.5)
        performance = self.test_performance(exec_content, has_bias=True)
        return performance.start_loop(self._icon_find)

    def end_point_with_icon(self, exec_content):
        performance = self.test_performance(exec_content)
        performance.end_loop(self._icon_find)
        time.sleep(0.5)  # 等待后续30张图片save完成
        self.extra_result = performance.result
        return 0


    def end_point_with_changed(self, exec_content):
        performance = self.test_performance(exec_content)
        performance.end_loop(self._picture_changed)
        time.sleep(0.5)  # 等待后续30张图片save完成
        self.extra_result = performance.result
        return 0


    def test_performance(self, exec_content, has_bias=False):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("areas")[0], data.get("threshold"),
                                        self.kwargs.get("work_path"), self.dq, bias=has_bias)
        return performance

    def test_performance_with_point(self, exec_content):
        body = exec_content.copy()
        body["functionName"] = "smart_icon_point_crop"
        request_dict = {
            "execCmdDict": body,
            "device_label": self._model.pk,
            "work_path": os.path.dirname(body.get("referImgFile"))
        }
        from app.v1.Cuttle.basic.basic_views import UnitFactory
        response = UnitFactory().create("ImageHandler", request_dict)
        return response

    def end_point_with_change(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        performance = PerformanceCenter(self._model.pk, None, data.get("areas")[0], data.get("threshold"),
                                        self.kwargs.get("work_path"), self.dq)
        performance.end_loop(self._pic_changed)
        time.sleep(1)
        return performance.result

    def _icon_find(self, picture, icon, threshold, disappear=False):
        feature_point_list = self.shape_identify(picture, icon)
        threshold = int((1 - threshold) * icon_rate)
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{icon_threshold_camera - threshold}")
        response = True if len(feature_point_list) >= (icon_threshold_camera - threshold) else False
        if disappear is True:
            response = bool(1 - response)
        return response

    def _picture_changed(self, last_pic, next_pic, threshold, changed=True):
        src_1 = cv2.imread(last_pic)
        src_2 = cv2.imread(next_pic)
        difference = np.absolute(np.subtract(src_1, src_2))
        result = np.count_nonzero(difference < 15)
        result2 = np.count_nonzero(245 < difference)
        standard = src_1.shape[0] * src_1.shape[1] * src_2.shape[2]
        match_ratio = ((result + result2) / standard)
        print("match_ratio:",match_ratio)
        final_result = match_ratio > threshold - 0.01
        if changed is True:
            final_result = bool(1 - final_result)
        return final_result

    def _pic_changed(self, picture, next_picture):
        pass
