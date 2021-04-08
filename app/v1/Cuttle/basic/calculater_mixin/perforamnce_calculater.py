import time

from app.v1.Cuttle.basic.image_schema import PerformanceSchema
from app.v1.Cuttle.basic.performance_center import PerformanceCenter


class PerformanceMinix(object):

    def start_point_with_icon(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("area"), self.kwargs.get("work_path"))
        return performance.start_loop(self.icon_find)

    def start_point_with_point(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("area"), self.kwargs.get("work_path"),bais=True)
        return performance.start_loop(self.icon_find)

    def end_point_with_icon(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        icon = self._crop_image(data.get("refer_im"), data.get("icon_areas")[0])
        performance = PerformanceCenter(self._model.pk, icon, data.get("area"), self.kwargs.get("work_path"))
        performance.end_loop(self.icon_find)
        time.sleep(2)
        return performance.result

    def end_point_with_change(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        performance = PerformanceCenter(self._model.pk, None, data.get("area"), self.kwargs.get("work_path"))
        performance.end_loop(self.pic_changed)
        time.sleep(2)
        return performance.result

    def icon_find(self, picture, icon):
        pass

    def pic_changed(self, picture, next_picture):
        pass
