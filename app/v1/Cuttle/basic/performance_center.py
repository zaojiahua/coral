import os
import time
from collections import deque
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.execption.outer.error_code.imgtool import VideoKeyPointNotFound
from app.v1.Cuttle.basic.operator.camera_operator import CameraMax, FpsMax
from app.v1.Cuttle.basic.setting import wait_bias
from redis_init import redis_client


class PerformanceCenter(object):

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, device_id, icon, scope, work_path,**kwargs):
        self.device_id = device_id
        self.result = 0
        self.back_up_dq = deque(maxlen=CameraMax)
        self.judge_icon = icon
        self.scope = scope
        self.move_flag = True
        self.loop_flag = True
        self.work_path = work_path
        self.kwargs = kwargs

    def start_loop(self, judge_function):
        executer = ThreadPoolExecutor()
        executer.submit(self.move_src_to_backup)
        number = 0
        self.start_number = 0
        while self.loop_flag:
            number, picture = self.picture_prepare(number)
            if judge_function(picture, self.judge_icon) == 0:
                if self.kwargs.get("bais") == True:
                    self.start_number = number - 1 + wait_bias
                else:
                    self.start_number = number - 1
                break
            if number >= CameraMax:
                self.move_flag = False
                raise VideoKeyPointNotFound
        return 0

    def end_loop(self, judge_function):
        number = self.start_number + 1
        while self.loop_flag:
            number, picture = self.picture_prepare(number)
            if judge_function(picture, self.judge_icon) == 0:
                self.end_number = number - 1
                self.result = {"start": self.start_number, "end": self.end_number,
                               "time": (self.end_number - self.start_number) * 1 / FpsMax}
                self.move_flag = False
                break
            if number >= CameraMax:
                self.move_flag = False
                raise VideoKeyPointNotFound
        return 0

    def picture_prepare(self, number):
        picture = self.back_up_dq.popleft()
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
            src = camera_dq_dict.get(self.device_id).popleft()
            src = cv2.imdecode(src, 1)
            src = np.rot90(src, 3)
            self.back_up_dq.append(src)
        # 找到结束点后再继续保存最多100张:
        number = self.end_number
        for i in range(100):
            try:
                src = self.back_up_dq.popleft()
                cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), src)
                number += 1
            except IndexError:
                return 0
        return 0

