import time
from collections import deque

from app.v1.Cuttle.basic.image_schema import PerformanceSchema
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax
from app.v1.Cuttle.basic.performance_center import PerformanceCenter
from app.v1.Cuttle.basic.setting import icon_threshold, icon_threshold_camera, icon_rate


class PerformanceMinix(object):
    dq = deque(maxlen=CameraMax)

    def start_point_with_icon(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("areas")[0], data.get("threshold"),
                                        self.kwargs.get("work_path"), self.dq)
        return performance.start_loop(self._icon_find)

    def start_point_with_point(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("areas")[0], data.get("threshold"),
                                        self.kwargs.get("work_path"), self.dq, bais=True, )
        return performance.start_loop(self._icon_find)

    def end_point_with_icon(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("areas")[0], data.get("threshold"),
                                        self.kwargs.get("work_path"), self.dq)
        performance.end_loop(self._icon_find)
        time.sleep(2)
        self.extra_result = performance.result
        return 0

    def end_point_with_change(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        performance = PerformanceCenter(self._model.pk, None, data.get("areas")[0], data.get("threshold"),
                                        self.kwargs.get("work_path"), self.dq)
        performance.end_loop(self._pic_changed)
        time.sleep(2)
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

    def _pic_changed(self, picture, next_picture):
        pass
