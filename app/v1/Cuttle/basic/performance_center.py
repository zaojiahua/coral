import os
import platform
import time
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.config.ip import HOST_IP
from app.execption.outer.error_code.imgtool import VideoStartPointNotFound, \
    VideoEndPointNotFound
from app.v1.Cuttle.basic.setting import FpsMax, CameraMax

sp = '/' if platform.system() == 'Linux' else '\\'


class PerformanceCenter(object):

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, device_id, icon_area, refer_im_path, scope, threshold, work_path: str, dq, **kwargs):
        self.device_id = device_id
        self.result = 0
        self.back_up_dq = dq
        # 使用黑色区域时，icon_scope为icon实际出现在snap图中的位置，使用icon surf时icon_scope为编辑时出现在refer图中的位置
        # 使用选区变化/不变时 icon_scope 为None
        # icon 和scope 这里都是相对的坐标
        self.icon_scope = icon_area[0] if isinstance(icon_area, list) else None
        self.judge_icon = self.get_icon(refer_im_path)
        self.scope = scope
        self.threshold = threshold
        self.move_flag = True
        self.loop_flag = True
        work_path = os.path.join(sp.join(os.path.dirname(work_path).split(sp)[:-1]), "performance") + sp
        if not os.path.exists(work_path):
            os.makedirs(work_path)
        self.work_path = work_path
        self.kwargs = kwargs

    def get_icon(self, refer_im_path):
        # 在使用黑色区域计算时，self.icon_scope为实际出现在snap图中的位置，此方法无意义
        # 在使用icon surf计算时，self.icon_scope为编辑时出现在refer图中的位置，此方拿到的是icon标准图
        if not all((refer_im_path, self.icon_scope)):
            return None
        picture = cv2.imread(refer_im_path)
        h, w = picture.shape[:2]
        area = [int(i) if i > 0 else 0 for i in
                [self.icon_scope[0] * w, self.icon_scope[1] * h, self.icon_scope[2] * w, self.icon_scope[3] * h]]
        return picture[area[1]:area[3], area[0]:area[2]]

    def start_loop(self, judge_function):
        self.back_up_dq.clear()
        executer = ThreadPoolExecutor()
        # 异步开始记录照片
        self.move_src_task = executer.submit(self.move_src_to_backup)
        number = 0
        self.start_number = 0
        # 等异步线程时间
        time.sleep(0.5)
        while self.loop_flag:
            use_icon_scope = True if judge_function.__name__ == "_black_field" else False
            number, picture, next_picture, _ = self.picture_prepare(number, use_icon_scope=use_icon_scope)
            pic2 = self.judge_icon if judge_function.__name__ in ("_icon_find", "_black_field") else next_picture
            if judge_function(picture, pic2, self.threshold) == True:
                self.bias = self.kwargs.get("bias") if self.kwargs.get("bias") else 0
                self.start_number = number - 1
                print(f"find start point number :{number - 1} start number:{self.start_number}")
                if judge_function.__name__ == "_black_field":
                    self.bias = self.bias + int((self.icon_scope[0] + self.icon_scope[2]) // 0.25)
                break
            if number >= CameraMax / 2:
                self.move_flag = False
                self.back_up_dq.clear()
                raise VideoStartPointNotFound
        return 0

    def end_loop(self, judge_function):
        if not hasattr(self, "start_number"):
            raise VideoStartPointNotFound
        number = self.start_number + 1
        b = time.time()
        print("end loop start... now number:", number)
        for i in range(self.bias):
            # 对bias补偿的帧数，先只保存对应图片，不做结果判断
            number, picture, next_picture, _ = self.picture_prepare(number)
        while self.loop_flag:
            number, picture, next_picture, _ = self.picture_prepare(number)
            pic2 = self.judge_icon if judge_function.__name__ == "_icon_find" else next_picture
            if judge_function(picture, pic2, self.threshold) == True:
                print(f"find end point number: {number}", self.bias)
                self.end_number = number - 1
                self.start_number = int(self.start_number + self.bias)
                self.result = {"start_point": self.start_number, "end_point": self.end_number,
                               "job_duration": max(round((self.end_number - self.start_number) * 1 / FpsMax, 3), 0),
                               "time_per_unit": round(1 / FpsMax, 4),
                               "picture_count": self.end_number + 29,
                               "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                self.move_flag = False
                break
            if number >= CameraMax / 2:
                self.result = {"start_point": self.start_number, "end_point": number,
                               "job_duration": max(round((number - self.start_number) * 1 / FpsMax, 3), 0),
                               "time_per_unit": round(1 / FpsMax, 4),
                               "picture_count": number,
                               "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                self.move_flag = False
                self.back_up_dq.clear()
                self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                raise VideoEndPointNotFound
        print("end loop time", time.time() - b)
        return 0

    def test_fps_lost(self, judge_function):
        if hasattr(self, "candidate"):
            delattr(self, "candidate")
        number = self.start_number + 1
        for i in range(200):
            number, picture, next_picture, next_next_picture = self.picture_prepare(number)
            pic2 = next_picture if self.kwargs.get("fps") >= 120 else next_next_picture
            if judge_function(picture, pic2, self.threshold) == False:
                # print(f"find end point number: {number}", "bias:", self.bias)
                # self.result = {"fps_lost": True, "lost_number": number}
                self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                if hasattr(self, "candidate") and number - self.candidate >= 3:
                    self.result = {"fps_lost": False,
                                   "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                    self.end_number = number - 1
                    self.move_flag = False
                    break
                elif hasattr(self, "candidate"):
                    continue
                else:
                    self.candidate = number
                    continue
            else:
                if hasattr(self, "candidate"):
                    self.result = {"fps_lost": True, "lost_number": self.candidate,
                                   "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                    self.end_number = number - 1
                    self.move_flag = False
                    break
            if number >= CameraMax / 3:
                self.move_flag = False
                self.back_up_dq.clear()
                raise VideoEndPointNotFound
        else:
            self.result = {"fps_lost": False}
            self.end_number = number - 1
            self.move_flag = False
        return 0

    def picture_prepare(self, number, use_icon_scope=False):
        # use_icon_scope为true时裁剪snap图中真实icon出现的位置
        # use_icon_scope为false时裁剪snap图中refer中标记的configArea选区大致范围
        for i in range(3):
            try:
                picture = self.back_up_dq.popleft()
                pic_next = self.back_up_dq[0]
                pic_next_next = self.back_up_dq[1]
                break
            except IndexError:
                time.sleep(0.02)
        # save_pic = cv2.resize(picture, dsize=(0, 0), fx=0.5, fy=0.5)
        cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), picture)
        number += 1
        h, w = picture.shape[:2]
        scope = self.scope if use_icon_scope is False else self.icon_scope
        area = [int(i) if i > 0 else 0 for i in [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]] \
            if 0 < all(i <= 1 for i in scope) else [int(i) for i in scope]
        picture = picture[area[1]:area[3], area[0]:area[2]]
        pic_next = pic_next[area[1]:area[3], area[0]:area[2]]
        pic_next_next = pic_next_next[area[1]:area[3], area[0]:area[2]]
        return number, picture, pic_next, pic_next_next

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
