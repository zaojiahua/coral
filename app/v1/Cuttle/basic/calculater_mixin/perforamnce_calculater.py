import os
import time
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.execption.outer.error import APIException
from app.execption.outer.error_code.imgtool import IconTooWeek, NotFindIcon
from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import PerformanceSchema, PerformanceSchemaCompare, PerformanceSchemaFps
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax
from app.v1.Cuttle.basic.performance_center import PerformanceCenter
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_rate, BIAS, SWIPE_BIAS
# from skimage.measure import compare_ssim
# from skimage.metrics.structural_similarity import compare_ssim
class PerformanceMinix(object):
    dq = deque(maxlen=CameraMax*2)

    def start_point_with_icon(self, exec_content):
        # 方法名字尚未变更，此为滑动检测起点的方法
        return self.swipe_calculate(exec_content, SWIPE_BIAS)

    def swipe_calculate(self, exec_content, bias):
        data = self._validate(exec_content, PerformanceSchema)
        # 获取用户的icon选区，按中心点重建边长为30的正方形选区
        x1 = data.get("icon_areas")[0][0]
        y1 = data.get("icon_areas")[0][1]
        x2 = data.get("icon_areas")[0][2]
        y2 = data.get("icon_areas")[0][3]
        icon_areas = [(x1 + x2) / 2 - 0.03, (y1 + y2) / 2 - 0.02, (x1 + x2) / 2 + 0.03, (y1 + y2) / 2 + 0.02]
        performance = PerformanceCenter(self._model.pk, [icon_areas], data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=bias)
        return performance.start_loop(self._black_field)

    def start_point_with_swipe_slow(self, exec_content):
        self.swipe_calculate(exec_content, BIAS)

    def start_point_with_point_template(self, exec_content):
        # 使用实际位置是否为黑色（机械臂遮挡）判定起始按下时间
        data = self._validate(exec_content, PerformanceSchema)
        content = exec_content.copy()
        # 获取refer图的size用于计算裁剪后的补偿
        src = cv2.imread(data.get("refer_im"))
        h, w = src.shape[:2]
        from app.v1.device_common.device_model import Device
        dev_obj = Device(pk=self._model.pk)
        # 获取手机截图下的size，把相对坐标换成截图下的绝对坐标
        d_h, d_w = dev_obj.device_height, dev_obj.device_width
        snap_x0, snap_y0 = int(data.get("areas")[0][0] * d_w), int(data.get("areas")[0][1] * d_h)
        # 先记录下裁剪位置的左上点拍摄图下的绝对坐标
        camera_x0, camera_y0 = int(data.get("areas")[0][0] * w), int(data.get("areas")[0][1] * h)
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            # 截图按选区先进行裁剪，再set进_pic_path
            ocr_obj._pic_path = self._crop_image_and_save(ocr_obj.default_pic_path, data["areas"][0])
            # 裁剪前的摄像头下的实际图片，赋值给Tguard的判定依据
            self.image = ocr_obj.default_pic_path
            # 此处得到的是icon在裁剪后的，摄像头下，图中的绝对坐标
            try:
                # ocr_obj.get_result_by_feature(content, cal_real_xy=False)
                ocr_obj.get_result_by_template_match(content, cal_real_xy=False)
            except NotFindIcon:
                return 1
            # +-camera_x0先换算到裁剪前摄像头图中的绝对坐标，这个数据用于起点的识别
            icon_real_position_camera = [ocr_obj.cx + camera_x0 - 20, ocr_obj.cy + camera_y0 - 20,
                                         ocr_obj.cx + camera_x0 + 20, ocr_obj.cy + camera_y0 + 20]
            # 此处换算到裁剪前的，截图下的坐标区域，这个数据用于驱动点击操作
            ocr_obj.cal_realy_xy(ocr_obj.cx, ocr_obj.cy, ocr_obj.default_pic_path)
            ocr_obj.add_bias(snap_x0, snap_y0)
            executer = ThreadPoolExecutor()
            # 异步延迟执行点击操作，确保另外一个线程的照片可以涵盖到这个操作
            exec_task = executer.submit(self.delay_exec, ocr_obj.point).add_done_callback(executor_callback)
            # 兼容其他多选区的格式，增加一层
            # 因为PerformanceCenter内部需要根据起点icon x方向位置，计算阴影补偿，所以此处再统一换回摄像头下的相对坐标
            data["icon_areas"] = [[icon_real_position_camera[0] / w, icon_real_position_camera[1] / h,
                                   icon_real_position_camera[2] / w, icon_real_position_camera[3] / h]]
            if self.kwargs.get("test_running"):  # 对试运行的unit只进行点击，不计算时间。
                return 0
        # 创建performance对象，
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"), self.dq, bias=BIAS)
        return performance.start_loop(self._black_field)

    def start_point_with_point(self, exec_content):
        # 使用实际位置是否为黑色（机械臂遮挡）判定起始按下时间
        data = self._validate(exec_content, PerformanceSchema)
        content = exec_content.copy()
        # 获取refer图的size用于计算裁剪后的补偿
        src = cv2.imread(data.get("refer_im"))
        h, w = src.shape[:2]
        from app.v1.device_common.device_model import Device
        dev_obj = Device(pk=self._model.pk)
        # 获取手机截图下的size，把相对坐标换成截图下的绝对坐标
        d_h, d_w = dev_obj.device_height, dev_obj.device_width
        snap_x0, snap_y0 = int(data.get("areas")[0][0] * d_w), int(data.get("areas")[0][1] * d_h)
        # 先记录下裁剪位置的左上点拍摄图下的绝对坐标
        camera_x0, camera_y0 = int(data.get("areas")[0][0] * w), int(data.get("areas")[0][1] * h)
        with Complex_Center(**self.kwargs) as ocr_obj:
            ocr_obj.snap_shot()
            # 截图按选区先进行裁剪，再set进_pic_path
            ocr_obj._pic_path = self._crop_image_and_save(ocr_obj.default_pic_path, data["areas"][0])
            # 裁剪前的摄像头下的实际图片，赋值给Tguard的判定依据
            self.image = ocr_obj.default_pic_path
            # 此处得到的是icon在裁剪后的，摄像头下，图中的绝对坐标
            try:
                # ocr_obj.get_result_by_feature(content, cal_real_xy=False)
                ocr_obj.get_result_by_feature(content, cal_real_xy=False)
            except NotFindIcon:
                return 1
            # +-camera_x0先换算到裁剪前摄像头图中的绝对坐标，这个数据用于起点的识别
            icon_real_position_camera = [ocr_obj.cx + camera_x0 - 30, ocr_obj.cy + camera_y0 - 30,
                                         ocr_obj.cx + camera_x0 + 30, ocr_obj.cy + camera_y0 + 30]
            # 此处换算到裁剪前的，截图下的坐标区域，这个数据用于驱动点击操作
            ocr_obj.cal_realy_xy(ocr_obj.cx, ocr_obj.cy, ocr_obj.default_pic_path)
            ocr_obj.add_bias(snap_x0, snap_y0)
            executer = ThreadPoolExecutor()
            # 异步延迟执行点击操作，确保另外一个线程的照片可以涵盖到这个操作
            exec_task = executer.submit(self.delay_exec, ocr_obj.point).add_done_callback(executor_callback)
            # 兼容其他多选区的格式，增加一层
            # 因为PerformanceCenter内部需要根据起点icon x方向位置，计算阴影补偿，所以此处再统一换回摄像头下的相对坐标
            data["icon_areas"] = [[icon_real_position_camera[0] / w, icon_real_position_camera[1] / h,
                                   icon_real_position_camera[2] / w, icon_real_position_camera[3] / h]]
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
        return self._end_point(exec_content, PerformanceSchema, self._icon_find)

    def end_point_with_icon_template_match(self, exec_content):
        return self._end_point(exec_content, PerformanceSchema, self._icon_find_template_match)

    def end_point_with_changed(self, exec_content):
        return self._end_point(exec_content, PerformanceSchemaCompare, self._picture_changed)

    def _end_point(self, exec_content, schema, judge_function):
        try:
            data = self._validate(exec_content, schema)
            performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                            data.get("areas")[0], data.get("threshold", 0.99),
                                            self.kwargs.get("work_path"), self.dq)
            performance.end_loop(judge_function)
            time.sleep(0.5)  # 等待后续30张图片save完成
            self.extra_result = performance.result
            return 0
        except APIException as e:
            self.image = performance.tguard_picture_path
            self.extra_result = performance.result if isinstance(performance.result, dict) else {}
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

    def _black_field(self, picture, _,__, threshold):
        result = np.count_nonzero(picture < 50)
        standard = picture.shape[0] * picture.shape[1] * picture.shape[2]
        # picture shape is 0?
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

    def _icon_find_template_match(self, picture, icon, threshold, disappear=False):
        response = self.template_match(picture, icon)
        if disappear is True:
            response = bool(1 - response)
        return response

    def _picture_changed(self, last_pic, next_pic,third_pic, threshold):
        # ssim_value = compare_ssim(last_pic,next_pic,multichannel=True,gaussian_weights=True)
        # print("ssim error:",ssim_value)
        # final_result =  float(ssim_value) > threshold
        # error = np.sum(np.subtract(last_pic,next_pic) **2)
        # error /= last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
        # print("mse error:",error)
        difference = np.absolute(np.subtract(last_pic, next_pic))
        result = np.count_nonzero(difference < 35)
        result2 = np.count_nonzero(220 < difference)
        standard = last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
        match_ratio = ((result + result2) / standard)
        final_result = match_ratio < threshold - 0.01
        if third_pic is not None:
            difference_2 = np.absolute(np.subtract(last_pic, third_pic))
            result_2 = np.count_nonzero(difference_2 < 30)
            result2_2 = np.count_nonzero(225 < difference_2)
            standard = last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
            match_ratio_2 = ((result_2 + result2_2) / standard)
            final_result_2 = match_ratio_2 < threshold - 0.03
        else:
            final_result_2 = True
            match_ratio_2 = 1
        return (final_result_2 and final_result) or match_ratio_2 < 0.9


    def delay_exec(self, function, *args, **kwargs):
        time.sleep(kwargs.get("sleep", 0.5))
        return function(*args, **kwargs)
