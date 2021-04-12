import os
import time
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.config.ip import HOST_IP
from app.execption.outer.error_code.imgtool import VideoKeyPointNotFound
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax, FpsMax
from app.v1.Cuttle.basic.setting import wait_bias, BIAS
from redis_init import redis_client


class PerformanceCenter(object):

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, device_id, icon, scope, threshold, work_path: str, dq, **kwargs):
        self.device_id = device_id
        self.result = 0
        self.back_up_dq = dq
        self.judge_icon = icon
        self.scope = scope
        self.threshold = threshold
        self.move_flag = True
        self.loop_flag = True
        work_path = "\\".join(os.path.dirname(work_path).split("\\")[:-1]) + "\\performance\\"
        if not os.path.exists(work_path):
            os.makedirs(work_path)
        self.work_path = work_path
        self.kwargs = kwargs

    def start_loop(self, judge_function):
        a = time.time()
        executer = ThreadPoolExecutor()
        self.move_src_task = executer.submit(self.move_src_to_backup)
        number = 0
        self.start_number = 0
        # 等异步线程时间
        time.sleep(0.5)
        while self.loop_flag:
            number, picture = self.picture_prepare(number)
            if judge_function(picture, self.judge_icon, self.threshold, disappear=True) == True:
                self.bias = True if self.kwargs.get("bias") == True else False
                self.start_number = number - 1
                print(f"find start point number :{number - 1} start number:{self.start_number}")
                break
            if number >= CameraMax / 2:
                self.move_flag = False
                self.back_up_dq.clear()
                raise VideoKeyPointNotFound
        print("start loop time", time.time() - a)
        return 0

    def end_loop(self, judge_function):
        number = self.start_number + 1
        b = time.time()
        print("end loop start... now number:", number)
        while self.loop_flag:
            number, picture = self.picture_prepare(number)
            if judge_function(picture, self.judge_icon, self.threshold) == True:
                print(f"find end point number: {number}", self.bias)
                self.end_number = number - 1
                self.start_number = self.start_number + BIAS if self.bias == True else self.start_number
                self.result = {"start": self.start_number, "end": self.end_number,
                               "time": round((self.end_number - self.start_number) * 1 / FpsMax, 4),
                               "time_per_unit": round(1 / FpsMax, 4),
                               "picture_root_url": HOST_IP+":5000"+self.work_path}
                self.move_flag = False
                break
            if number >= CameraMax / 2:
                self.move_flag = False
                self.back_up_dq.clear()
                raise VideoKeyPointNotFound
        print("end loop time", time.time() - b)
        return 0

    def picture_prepare(self, number):
        for i in range(3):
            try:
                picture = self.back_up_dq.popleft()
                break
            except IndexError:
                time.sleep(0.02)
        cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), picture)
        number += 1
        h, w = picture.shape[:2]
        area = [int(i) if i > 0 else 0 for i in
                [self.scope[0] * w, self.scope[1] * h, self.scope[2] * w, self.scope[3] * h]]
        picture = picture[area[1]:area[3], area[0]:area[2]]
        return number, picture

    def move_src_to_backup(self):
        # 把dq内图片放置到备用dq中去，此方法在起始点判定时异步开始执行，到终止点判定结束退出
        self.move_flag = True
        from app.v1.Cuttle.basic.setting import camera_dq_dict
        camera_dq_dict.get(self.device_id).clear()
        time.sleep(2 / FpsMax)  # 确保dq里至少一张照片
        while self.move_flag:
            try:
                src = camera_dq_dict.get(self.device_id).popleft()
                src = cv2.imdecode(src, 1)
                src = np.rot90(src, 3)
                self.back_up_dq.append(src)
            except IndexError as e:
                # 向备份Q中放置过快,超过摄像头读取速度，需要等待一帧时间
                time.sleep(2 / FpsMax)
        print(f"move src thread stop... save 30 more..")
        # 找到结束点后再继续保存最多30张:
        number = self.end_number
        for i in range(30):
            try:
                src = self.back_up_dq.popleft()
                cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), src)
                number += 1
            except IndexError as e:
                print(repr(e))
                return 0
        self.back_up_dq.clear()
        return 0
