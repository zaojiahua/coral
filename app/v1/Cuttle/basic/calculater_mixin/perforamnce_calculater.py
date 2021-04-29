import os
import time
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.execption.outer.error import APIException
from app.execption.outer.error_code.imgtool import IconTooWeek, NotFindIcon
from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.image_schema import PerformanceSchema, PerformanceSchemaCompare, PerformanceSchemaFps
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax
from app.v1.Cuttle.basic.performance_center import PerformanceCenter
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_rate, BIAS, SWIPE_BIAS


class PerformanceMinix(object):
    dq = deque(maxlen=CameraMax)

    def start_point_with_icon(self, exec_content):
        # 方法名字尚未变更，此为滑动检测起点的方法
        data = self._validate(exec_content, PerformanceSchema)
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=SWIPE_BIAS)
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
            try:
                ocr_obj.get_result_by_feature(content, cal_real_xy=False)
            except NotFindIcon:
                return 1
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
            if self.kwargs.get("test_running"):  # 对试运行的unit只进行点击，不计算时间。
                return 0
        # 创建performance对象，
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=BIAS)
        return performance.start_loop(self._black_field)

    def start_point_with_point_fixed(self, exec_content):
        data = self._validate(exec_content, PerformanceSchemaCompare)
        x1, y1, x2, y2 = data.get("areas")[0]
        x = (x1 + x2) / 2
        y = (y1 + y2) / 2
        request_body = {
            "device_label": self._model.pk,
            "execCmdList": [f"shell input tap {x} {y}"]
        }
        # request_body.update({"ignore_arm_reset": True})
        from app.v1.Cuttle.basic.basic_views import UnitFactory
        executer = ThreadPoolExecutor()
        executer.submit(self.delay_exec, UnitFactory().create, "HandHandler", request_body).add_done_callback(
            executor_callback)
        performance = PerformanceCenter(self._model.pk, data.get("areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=BIAS)
        return performance.start_loop(self._black_field)

    def end_point_with_icon(self, exec_content):
        try:
            data = self._validate(exec_content, PerformanceSchema)
            performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                            data.get("areas")[0], data.get("threshold", 0.99),
                                            self.kwargs.get("work_path"), self.dq)
            performance.end_loop(self._icon_find)
            time.sleep(0.5)  # 等待后续30张图片save完成
            self.extra_result = performance.result
            return 0
        except APIException as e:
            self.image = performance.tguard_picture_path
            return 1

    def end_point_with_changed(self, exec_content):
        try:
            data = self._validate(exec_content, PerformanceSchemaCompare)
            performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                            data.get("areas")[0], data.get("threshold", 0.99),
                                            self.kwargs.get("work_path"), self.dq)
            performance.end_loop(self._picture_changed)
            time.sleep(0.5)  # 等待后续30张图片save完成
            # performance.result["end_point"] += 1
            # performance.result["job_duration"] = performance.result["job_duration"] + performance.result[
            #     "time_per_unit"]
            self.extra_result = performance.result
            return 0
        except APIException as e:
            self.image = performance.tguard_picture_path
            return 1

    def start_point_with_fps_lost(self, exec_content):
        data = self._validate(exec_content, PerformanceSchemaCompare)
        performance = PerformanceCenter(self._model.pk, None, None,
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq)
        return performance.start_loop(self._picture_changed)

    def end_point_with_fps_lost(self, exec_content):
        try:
            data = self._validate(exec_content, PerformanceSchemaFps)
            performance = PerformanceCenter(self._model.pk, None, None,
                                            data.get("areas")[0], data.get("threshold", 0.99),
                                            self.kwargs.get("work_path"), self.dq, fps=data.get("fps"))
            performance.test_fps_lost(self._picture_changed)
            self.extra_result = performance.result
            result = 0 if performance.result.get("fps_lost") == False else 1
            self.image = performance.tguard_picture_path
            return result
        except APIException as e:
            self.image = performance.tguard_picture_path
            return 1

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
        result = np.count_nonzero(picture < 50)
        standard = picture.shape[0] * picture.shape[1] * picture.shape[2]
        match_ratio = result / standard
        return match_ratio > threshold - 0.01

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
        result = np.count_nonzero(difference < 35)
        result2 = np.count_nonzero(220 < difference)
        standard = last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
        match_ratio = ((result + result2) / standard)
        print(match_ratio)
        final_result = match_ratio > threshold - 0.01
        if changed is True:
            final_result = bool(1 - final_result)
        return final_result

    def delay_exec(self, function, *args, **kwargs):
        time.sleep(kwargs.get("sleep", 0.5))
        return function(*args, **kwargs)
