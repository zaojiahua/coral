import os
import time
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.execption.outer.error import APIException
from app.execption.outer.error_code.imgtool import IconTooWeek, NotFindIcon
from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.complex_center import Complex_Center
from app.v1.Cuttle.basic.image_schema import PerformanceSchema, PerformanceSchemaCompare, PerformanceSchemaFps
from app.v1.Cuttle.basic.performance_center import PerformanceCenter
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_rate
from app.config.setting import CORAL_TYPE
from redis_init import redis_client


class PerformanceMinix(object):
    def start_point_with_icon(self, exec_content):
        # 方法名字尚未变更，此为滑动检测起点的方法
        return self.swipe_calculate(exec_content)

    def swipe_calculate(self, exec_content):
        data = self._validate(exec_content, PerformanceSchema)
        # 获取用户的icon选区，按中心点重建边长为30的正方形选区，如果机械臂的延长角铁变细这个可以随着做一些变化
        x1 = data.get("icon_areas")[0][0]
        y1 = data.get("icon_areas")[0][1]
        x2 = data.get("icon_areas")[0][2]
        y2 = data.get("icon_areas")[0][3]
        icon_areas = [(x1 + x2) / 2 - 0.03, (y1 + y2) / 2 - 0.02, (x1 + x2) / 2 + 0.03, (y1 + y2) / 2 + 0.02]
        performance = PerformanceCenter(self._model.pk, [icon_areas], data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"))
        return performance.start_loop(self.kwargs.get('start_method', 1) - 1)

    def start_point_with_swipe_slow(self, exec_content):
        self.swipe_calculate(exec_content)

    def start_point_with_point_template(self, exec_content):
        # 点击相应的主要使用方法
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
            # 裁剪前的摄像头下的实际图片，赋值给Tguard的判定依据（2021-11-14更新，这步已经没有用了）
            self.image = ocr_obj.default_pic_path
            # 此处得到的是icon在裁剪后的，摄像头下，图中的绝对坐标
            try:
                # ocr_obj.get_result_by_feature(content, cal_real_xy=False)
                ocr_obj.get_result_by_template_match(content, cal_real_xy=False)
            except NotFindIcon as e:
                return 1
            # +-camera_x0先换算到裁剪前摄像头图中的绝对坐标，这个数据用于起点的识别
            icon_real_position_camera = [ocr_obj.cx + camera_x0 - 20, ocr_obj.cy + camera_y0 - 20,
                                         ocr_obj.cx + camera_x0 + 20, ocr_obj.cy + camera_y0 + 20]
            # 此处换算到裁剪前的，截图下的坐标区域，这个数据用于驱动点击操作
            ocr_obj.cal_realy_xy(ocr_obj.cx, ocr_obj.cy, ocr_obj.default_pic_path)
            ocr_obj.add_bias(snap_x0, snap_y0)
            executer = ThreadPoolExecutor()
            # 异步延迟执行点击操作，确保另外一个线程的照片可以涵盖到这个操作
            executer.submit(self.delay_exec,
                            ocr_obj.point,
                            is_init=True)\
                .add_done_callback(executor_callback)
            # 兼容其他多选区的格式，增加一层
            # 因为PerformanceCenter内部需要根据起点icon x方向位置，计算阴影补偿，所以此处再统一换回摄像头下的相对坐标
            data["icon_areas"] = [[icon_real_position_camera[0] / w, icon_real_position_camera[1] / h,
                                   icon_real_position_camera[2] / w, icon_real_position_camera[3] / h]]
            if self.kwargs.get("test_running"):  # 对试运行的unit只进行点击，不计算时间。
                return 0

        # 创建performance对象，并开始找起始点
        performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"))
        return performance.start_loop(self.kwargs.get('start_method', 1) - 1)

    def start_point_with_point(self, exec_content):
        # 跟上面那个方法差不多，就是把模板匹配换成surf特征了，其实可以重构时候做些合并
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

        # 实时截图
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
                                        self.kwargs.get("work_path"))
        return performance.start_loop(self.kwargs.get('start_method', 1) - 1)

    def start_point_with_point_fixed(self, exec_content):
        # 与上面两个方法也差不多，不做图标搜索了，就是按给的图标位置直接按，适合特别难识别的图标，但没有抵抗变化的能力
        data = self._validate(exec_content, PerformanceSchemaCompare)
        x1, y1, x2, y2 = data.get("areas")[0]
        x = (x1 + x2) / 2
        y = (y1 + y2) / 2
        request_body = {
            "device_label": self._model.pk,
            "execCmdList": [f"shell input tap {x} {y}"],
            'is_init': True
        }
        # request_body.update({"ignore_arm_reset": True})
        from app.v1.Cuttle.basic.basic_views import UnitFactory
        executer = ThreadPoolExecutor()
        executer.submit(self.delay_exec, UnitFactory().create, "HandHandler", request_body).add_done_callback(
            executor_callback)
        if self.kwargs.get("test_running"):
            return 0
        performance = PerformanceCenter(self._model.pk, data.get("areas"), data.get("refer_im"),
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"))
        return performance.start_loop(self.kwargs.get('start_method', 1) - 1)

    # 下面几个就是上面那几个结束点版本
    def end_point_with_icon(self, exec_content):
        return self._end_point(exec_content, PerformanceSchema, self._icon_find)

    def end_point_with_icon_template_match(self, exec_content):
        return self._end_point(exec_content, PerformanceSchema, self._icon_find_template_match)

    def end_point_with_changed(self, exec_content):
        return self._end_point(exec_content, PerformanceSchemaCompare, self._picture_changed)

    def end_point_with_blank(self, exec_content):
        return self._end_point(exec_content, PerformanceSchema, self._is_blank)

    @staticmethod
    def wait_end():
        # 当发生异常的时候，另一个进程可能还在使用相机，所以这里等待几秒再返回，防止t-guard马上使用相机
        # 这里简单判断一个相机即可
        while redis_client.get(f"g_bExit_0") == "0":
            time.sleep(0.1)

    def _end_point(self, exec_content, schema, judge_function):
        keep_pic = [2017]
        try:
            data = self._validate(exec_content, schema)

            # 测试unit 目前只有检测黑屏会走这里
            if self.kwargs.get("test_running"):
                refer_im = cv2.imread(data.get("refer_im"))
                h, w, _ = refer_im.shape
                scope = data.get("icon_areas")[0]
                area = [int(i) if i > 0 else 0 for i in [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]]
                img = refer_im[area[1]:area[3], area[0]:area[2]]
                threshold = data.get("threshold", 0.99)
                ret = judge_function(img, None, None, threshold)
                return 0 if ret else 1

            performance = PerformanceCenter(self._model.pk, data.get("icon_areas"), data.get("refer_im"),
                                            data.get("areas")[0], data.get("threshold", 0.99),
                                            self.kwargs.get("work_path"))
            performance.end_loop(judge_function)
            self.extra_result = performance.result
            return 0
        except APIException as e:
            self.image = performance.tguard_picture_path if hasattr(performance, "tguard_picture_path") else None
            self.extra_result = performance.result if isinstance(performance.result, dict) else {}
            self.wait_end()
            if hasattr(e, 'error_code'):
                if e.error_code in keep_pic:
                    return 1
                else:
                    return e.error_code
            return 1
        except Exception as e:
            self.wait_end()
            raise e

    def start_point_with_fps_lost(self, exec_content):
        data = self._validate(exec_content, PerformanceSchemaCompare)
        performance = PerformanceCenter(self._model.pk, None, None,
                                        data.get("areas")[0], data.get("threshold", 0.99),
                                        self.kwargs.get("work_path"))
        return performance.start_loop(self._picture_changed)

    def end_point_with_fps_lost(self, exec_content):
        try:
            data = self._validate(exec_content, PerformanceSchemaFps)
            performance = PerformanceCenter(self._model.pk, None, None,
                                            data.get("areas")[0], data.get("threshold", 0.99),
                                            self.kwargs.get("work_path"), fps=data.get("fps"))
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

    def _icon_find(self, picture, icon, _, threshold, disappear=False):
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

    def _icon_find_template_match(self, picture, icon, next_pic, th):
        # 这个是用来做阈值过滤的方法
        # self.template_match_temp 返回的是模板匹配后得到的max value值
        # 这个值越接近1代表匹配的结果越接近
        max_value_1 = self.template_match_temp(picture, icon)
        # 这部分主要有历史原因，因为之前的用例阈值都默认给了99%，所以向下调可以98%，97% 但是向上只能99.5% 99.9%这样
        # 由于上下调整的幅度不一致（差一位）,所以这块做了区别处理，让其调整的幅度变成相同的。
        # 统一原则是th变大--> 此方法判定严格-->最后得到的点延后
        if 0.999 >= th > 0.99:
            th = (1 - th) * 10 + 0.99
        elif 1 >= th > 0.999:
            th = 1.08
        corr_th = 0.1 + (1 - th)
        result_1 = (1 - np.abs(max_value_1)) < corr_th
        # print((1 - np.abs(max_value_1)))
        return result_1

    def _picture_changed(self, last_pic, next_pic, third_pic, threshold, fps_lost=False):
        # LOW TH -->  EASY TO
        # ssim_value = compare_ssim(last_pic,next_pic,multichannel=True,gaussian_weights=True)
        # print("ssim error:",ssim_value)
        # final_result =  float(ssim_value) > threshold
        # error = np.sum(np.subtract(last_pic,next_pic) **2)
        # error /= last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
        # print("mse error:",error)
        # 这个方法和上面一样，也是调节了阈值的范围，让向下和向上变成相同的力度。
        if 0.999 >= threshold > 0.99:
            threshold = (1 - threshold) * 10 + 0.99
        elif 1 >= threshold > 0.999:
            threshold = 1.08

        difference = np.absolute(np.subtract(last_pic, next_pic))
        result = np.count_nonzero(difference < 25)
        result2 = np.count_nonzero(230 < difference)
        standard = last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
        match_ratio = ((result + result2) / standard)
        final_result = match_ratio < (1.97-threshold)
        if third_pic is not None:
            difference_2 = np.absolute(np.subtract(last_pic, third_pic))
            result_2 = np.count_nonzero(difference_2 < 25)
            result2_2 = np.count_nonzero(230 < difference_2)
            standard = last_pic.shape[0] * last_pic.shape[1] * last_pic.shape[2]
            match_ratio_2 = ((result_2 + result2_2) / standard)
            final_result_2 = match_ratio_2 < (1.95-threshold)
        else:
            final_result_2 = True
            match_ratio_2 = 1
        if fps_lost:
            return not (not final_result and not final_result_2)
        # print(match_ratio_2,match_ratio)
        return (final_result_2 and final_result) or match_ratio_2 < (1.94-threshold)

    def delay_exec(self, function, *args, **kwargs):
        # 5双摄升级版的柜子，机械臂离设备比较近，等待时间需要长一点，否则机械臂按完以后压力传感器才开始获取压力值
        if CORAL_TYPE == 5:
            time.sleep(kwargs.get("sleep", 1.3))
        else:
            time.sleep(kwargs.get("sleep", 0.3))
        return function(*args, **kwargs)

    def _is_blank(self, pic, next_pic, third_pic, threshold):
        # cv2.imwrite('result_0.png', pic)
        pic = cv2.cvtColor(pic, cv2.COLOR_BGR2GRAY)
        ret, binary = cv2.threshold(pic, 50, 255, cv2.THRESH_BINARY)
        # cv2.imwrite('result.png', binary)

        w, h = binary.shape
        nonzero_count = np.count_nonzero(binary)
        all_pixes = w * h
        blank_rate = (all_pixes - nonzero_count) / all_pixes
        if blank_rate > threshold:
            return 1
        else:
            return 0
