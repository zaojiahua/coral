import os
import time
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.execption.outer.error_code.imgtool import IconTooWeek
from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.common_utli import judge_pic_same
from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.image_schema import PerformanceSchema, PerformanceSchemaCompare
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax
from app.v1.Cuttle.basic.performance_center import PerformanceCenter
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_rate


class PerformanceMinix(object):
    dq = deque(maxlen=CameraMax)

    def start_point_with_icon(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=True)
        return performance.start_loop(self._black_field)

    def start_point_with_point(self, exec_content):
        # 使用实际位置是否为黑色（机械臂遮挡）判定起始按下时间
        data = self._validate(exec_content, PerformanceSchema)
        content = exec_content.copy()
        src = cv2.imread(data.get("refer_im"))
        h, w = src.shape[:2]
        from app.v1.device_common.device_model import Device
        dev_obj = Device(pk=self._model.pk)
        d_h, d_w = dev_obj.device_height, dev_obj.device_width
        snap_x0, snap_y0 = int(data.get("areas")[0][0] * d_w), int(data.get("areas")[0][1] * d_h)
        # 先记录下裁剪位置的左上点的绝对坐标
        camera_x0, camera_y0 = int(data.get("areas")[0][0] * w), int(data.get("areas")[0][1] * h)
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            # 截图按选区先进行裁剪，再set进_pic_path
            ocr_obj._pic_path = self._crop_image_and_save(ocr_obj.default_pic_path, data["areas"][0])
            self.image = ocr_obj.default_pic_path
            # 此处得到的是裁剪后icon在图中的绝对坐标
            ocr_obj.get_result_by_feature(content, cal_real_xy=False)
            # 摄像头下,完整图的,实际坐标区域,中心点加减范围
            icon_real_position_camera = [ocr_obj.cx + camera_x0 - 30, ocr_obj.cy + camera_y0 - 30,
                                         ocr_obj.cx + camera_x0 + 30, ocr_obj.cy + camera_y0 + 30]
            # 截图下,完整图的,实际坐标区域
            ocr_obj.cal_realy_xy(ocr_obj.cx, ocr_obj.cy, ocr_obj.default_pic_path)
            ocr_obj.add_bias(snap_x0, snap_y0)
            executer = ThreadPoolExecutor()
            # 异步延迟执行点击操作，确保另外一个线程的照片可以涵盖到这个操作
            exec_task = executer.submit(self.delay_exec, ocr_obj.point).add_done_callback(executor_callback)
            # 兼容其他多选区的格式，增加一层
            data["icon_areas"] = [icon_real_position_camera]
        # 创建performance对象，
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=True)
        return performance.start_loop(self._black_field)

    def end_point_with_icon(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        performance =  PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                 data.get("areas")[0], data.get("threshold", 0.99),
                                 self.kwargs.get("work_path"), self.dq, bias=False)
        performance.end_loop(self._icon_find)
        time.sleep(0.5)  # 等待后续30张图片save完成
        self.extra_result = performance.result
        return 0

    def end_point_with_changed(self, exec_content):
        data = self._validate(exec_content, PerformanceSchemaCompare)
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=False)
        performance.end_loop(self._picture_changed)
        time.sleep(0.5)  # 等待后续30张图片save完成
        performance.result["end_point"] += 1
        performance.result["job_duration"] = performance.result["job_duration"] + performance.result["time_per_unit"]
        self.extra_result = performance.result
        return 0

    # def test_performance(self, exec_content, has_bias=False, schema=PerformanceSchemaCompare):
    #     data = self._validate(exec_content, schema)
    #     return PerformanceCenter(self._model.pk, data.get("icon_areas")[0], data.get("refer_im"),
    #                              data.get("areas"), data.get("threshold", 0.99),
    #                              self.kwargs.get("work_path"), self.dq, bias=has_bias)

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

    def _black_field(self, picture, _, threshold):
        result = np.count_nonzero(picture < 40)
        standard = picture.shape[0] * picture.shape[1] * picture.shape[2]
        match_ratio = result / standard
        return match_ratio > threshold - 0.2

    def _icon_find(self, picture, icon, threshold, disappear=False):
        try:
            feature_point_list = self.shape_identify(picture, icon)
        except IconTooWeek:
            return False
        threshold = int((1 - threshold) * icon_rate)
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{icon_threshold_camera - threshold}")
        response = True if len(feature_point_list) >= (icon_threshold_camera - threshold) else False
        if disappear is True:
            response = bool(1 - response)
        return response

    def _picture_changed(self, last_pic, next_pic, threshold, changed=True):
        difference = np.absolute(np.subtract(last_pic, next_pic))
        result = np.count_nonzero(difference < 15)
        result2 = np.count_nonzero(245 < difference)
        standard = last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
        match_ratio = ((result + result2) / standard)
        final_result = match_ratio > threshold - 0.05
        if changed is True:
            final_result = bool(1 - final_result)
        return final_result

    def delay_exec(self, function, **kwargs):
        time.sleep(kwargs.get("sleep", 0.5))
        return function(**kwargs)
