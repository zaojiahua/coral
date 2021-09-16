import os
import platform
import time
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
import numpy as np

from app.config.ip import HOST_IP
from app.execption.outer.error_code.imgtool import VideoStartPointNotFound, \
    VideoEndPointNotFound, FpsLostWrongValue, PerformanceNotStart
from app.v1.Cuttle.basic.setting import FpsMax, CameraMax

sp = '/' if platform.system() == 'Linux' else '\\'


class PerformanceCenter(object):
    # 这部分是性能测试的中心对象，性能测试主要测试启动点 和终止点两个点位，并根据拍照频率计算实际时间
    # 终止点比较简单，但是启动点由于现有机械臂无法确认到具体点压的时间，只能通过机械臂遮挡关键位置时间+补偿时间（机械臂下落按压时间）计算得到
    # 补偿时间又区分出多种情况，点击普通滑动 和用力滑动，第一接触点位置位于屏幕x方向的位置（摄像头角度），需要分别计算补偿的帧数。
    def __new__(cls, *args, **kwargs):
        # 单例
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, device_id, icon_area, refer_im_path, scope, threshold, work_path: str, dq, **kwargs):
        self.device_id = device_id
        self.result = 0
        # dq存储起始点前到终止点后的每一帧图片
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
        # 计算起始点的方法
        self.back_up_dq.clear()
        executer = ThreadPoolExecutor()
        # 先清空back_up_dq并异步开始记录照片
        self.move_src_task = executer.submit(self.move_src_to_backup)
        number = 0
        self.start_number = 0
        # 等异步线程时间，确认back_up_dq已经有了一些照片
        time.sleep(0.2)
        while self.loop_flag:
            use_icon_scope = True if judge_function.__name__ == "_black_field" else False
            # 裁剪图片获取当前和下一张
            # number, picture, next_picture, _ = self.picture_prepare(number, use_icon_scope=use_icon_scope)
            number, picture, next_picture, third_pic = self.picture_prepare(number, use_icon_scope=use_icon_scope)
            pic2 = self.judge_icon if judge_function.__name__ in ("_icon_find", "_black_field") else next_picture
            # judge_function 返回True时 既是发现了起始点
            # if judge_function(picture, pic2, self.threshold) == True:
            if judge_function(picture, pic2, third_pic, self.threshold) == True:
                self.bias = self.kwargs.get("bias") if self.kwargs.get("bias") else 0
                self.start_number = number - 1
                print(f"find start point number :{number - 1} start number:{self.start_number}")
                if judge_function.__name__ == "_black_field":
                    # 除了查询丢帧情况，都要计算bias，既补偿的帧数，这部分是根据第一点击点的x位置，给一个线性的补偿。后续可以考虑优化成多项式
                    # self.bias = self.bias + int((self.icon_scope[0] + self.icon_scope[2]) // 0.4)
                    # print(int((self.icon_scope[0] + self.icon_scope[2]) // (35 / FpsMax)))
                    self.bias = self.bias + int((self.icon_scope[0] + self.icon_scope[2]) // (50 / FpsMax))
                break
            if number >= CameraMax / 2:
                # 很久都没找到起始点的情况下，停止复制图片，清空back_up_dq，抛异常
                self.move_flag = False
                self.back_up_dq.clear()
                self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                raise VideoStartPointNotFound
        return 0

    def end_loop(self, judge_function):
        # 计算终止点的方法
        if not hasattr(self, "start_number"):
            # 计算终止点前一定要保证已经有了起始点，不可以单独调用或在计算起始点结果负值时调用。
            raise VideoStartPointNotFound
        number = self.start_number + 1
        print("end loop start... now number:", number, "bias:", self.bias)
        if len(self.back_up_dq) == 0:
            raise PerformanceNotStart
        if self.bias > 0:
            for i in range(self.bias):
                # 对bias补偿的帧数，先只保存对应图片，不做结果判断
                number, picture, next_picture, _ = self.picture_prepare(number)
        while self.loop_flag:
            number, picture, next_picture, third_pic = self.picture_prepare(number)
            number, picture, next_picture, third_pic = self.picture_prepare(number)
            if judge_function.__name__ in ["_icon_find", "_icon_find_template_match"]:
                pic2 = self.judge_icon
                third_pic = next_picture
            else:
                pic2 = next_picture
                third_pic = third_pic
            if judge_function(picture, pic2, third_pic, self.threshold) == True:
                print(f"find end point number: {number}", self.bias)
                # 找到终止点后，包装一个json格式，推到reef。
                # end point draw pic...
                self.end_number = number - 1
                if not judge_function.__name__ in ["_icon_find", "_icon_find_template_match"]:
                    self.draw_rec = True
                    end = self.end_number + 1
                else:
                    self.draw_line_in_pic(number, picture)
                    end = self.end_number
                self.start_number = int(self.start_number + self.bias)
                self.result = {"start_point": self.start_number, "end_point": end,
                               "job_duration": max(round((self.end_number - self.start_number) * 1 / FpsMax, 3), 0),
                               "time_per_unit": round(1 / FpsMax, 4),
                               "picture_count": self.end_number + 39,
                               "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                self.move_flag = False
                break
            if number >= CameraMax / 2:
                self.result = {"start_point": self.start_number + self.bias, "end_point": number,
                               "job_duration": max(round((number - self.start_number) * 1 / FpsMax, 3), 0),
                               "time_per_unit": round(1 / FpsMax, 4),
                               "picture_count": number,
                               "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                self.move_flag = False
                self.back_up_dq.clear()
                self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                raise VideoEndPointNotFound
        return 0

    def draw_line_in_pic(self, number, picture):
        # 在结尾图片上画上选框（可能是画图标，也可能是画判定选区）
        is_icon = not (self.icon_scope is None or len(self.icon_scope) < 1)
        scope = self.icon_scope if is_icon else self.scope
        h, w = picture.shape[:2]
        area = [int(i) if i > 0 else 0 for i in
                [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]] \
            if 0 < all(i <= 1 for i in scope) else [int(i) for i in scope]
        x1, y1 = area[:2]
        x4, y4 = area[2:]
        pic = picture.copy()
        if is_icon and self.scope != [0, 0, 1, 1]:  # 需要画的是图标，但是需要在已有选区（裁剪后）的图片上画，所以需要换算
            x1 = x1 - self.scope[0] * w
            y1 = y1 - self.scope[1] * h
            x4 = x4 - self.scope[0] * w
            y4 = y4 - self.scope[1] * h
        cv2.rectangle(pic, (x1, y1), (x4, y4), (0, 255, 0), 4)
        cv2.imwrite(os.path.join(self.work_path, f"{number - 1}.jpg"), pic)

    def test_fps_lost(self, judge_function):
        # 丢帧检测的单独方法，原理是看滑动时没帧图片是不是和上一帧相同，
        # 同样由于机械臂硬件无法获取终止滑动的时间，所以与上一帧相同的图片可能为丢帧，也可能为滑动已经停止
        # 需要设定为候选candidate，再继续看后续后面连续几（5）帧，如果都不变默认为已经停止
        if self.kwargs.get("fps") not in [60, 90, 120]:
            raise FpsLostWrongValue
        if hasattr(self, "candidate"):
            delattr(self, "candidate")
        number = self.start_number + 1
        skip = 2 if self.kwargs.get("fps") == 120 else 4
        for i in range(FpsMax * 3):
            number, picture_original, picture_comp_1, picture_comp_2 = self.picture_prepare_for_fps_lost(number, skip)
            if judge_function(picture_original, picture_comp_1, picture_comp_2, min(self.threshold + 0.005, 1),
                              fps_lost=True) == False:
                self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                if hasattr(self, "candidate") and number - self.candidate >= skip * 4:
                    self.result = {"fps_lost": False,
                                   "picture_count": number + 29,
                                   "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                    self.end_number = number
                    self.move_flag = False
                    break
                elif hasattr(self, "candidate"):
                    continue
                else:
                    self.candidate = number - 1
                    continue
            else:
                if hasattr(self, "candidate"):
                    self.result = {"fps_lost": True, "lose_frame_point": self.candidate,
                                   "picture_count": number + 29,
                                   "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                    self.end_number = number
                    self.move_flag = False
                    break
            if number >= CameraMax / 2:
                self.move_flag = False
                self.back_up_dq.clear()
                raise VideoEndPointNotFound
        else:
            self.result = {"fps_lost": False}
            self.end_number = number
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
            except IndexError as e:
                print("error in picture_prepare", repr(e))
                time.sleep(0.2)
        picture_save = cv2.resize(picture, dsize=(0, 0), fx=0.7, fy=0.7)
        cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), picture_save)
        number += 1
        h, w = picture.shape[:2]
        scope = self.scope if use_icon_scope is False else self.icon_scope
        area = [int(i) if i > 0 else 0 for i in [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]] \
            if 0 < all(i <= 1 for i in scope) else [int(i) for i in scope]
        picture = picture[area[1]:area[3], area[0]:area[2]]
        pic_next = pic_next[area[1]:area[3], area[0]:area[2]]
        pic_next_next = pic_next_next[area[1]:area[3], area[0]:area[2]]
        return number, picture, pic_next, pic_next_next

    def picture_prepare_for_fps_lost(self, number, skip=2):
        for i in range(3):
            try:
                for i in range(skip + 1):
                    pic = self.back_up_dq.popleft()
                    if i == 0:
                        pic_original = pic
                    elif i == skip:
                        pic_compare_1 = pic
                    cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), pic)
                    number += 1
                pic_compare_2 = self.back_up_dq[skip - 1]
                break
            except IndexError as e:
                print("error in picture_prepare", repr(e))
                time.sleep(0.05)
        h, w = pic_original.shape[:2]
        area = [int(i) if i > 0 else 0 for i in
                [self.scope[0] * w, self.scope[1] * h, self.scope[2] * w, self.scope[3] * h]] \
            if 0 < all(i <= 1 for i in self.scope) else [int(i) for i in self.scope]
        pic_original = pic_original[area[1]:area[3], area[0]:area[2]]
        pic_compare_1 = pic_compare_1[area[1]:area[3], area[0]:area[2]]
        pic_compare_2 = pic_compare_2[area[1]:area[3], area[0]:area[2]]
        return number, pic_original, pic_compare_1, pic_compare_2

    def move_src_to_backup(self):
        # 把dq内图片放置到备用dq中去，此方法在起始点判定时异步开始执行，到终止点判定结束退出
        self.move_flag = True
        from app.v1.Cuttle.basic.setting import camera_dq_dict
        camera_dq_dict.get(self.device_id).clear()
        time.sleep(2 / FpsMax)  # 确保dq里至少一张照片
        while self.move_flag:
            try:
                src = camera_dq_dict.get(self.device_id).popleft()
                # src = cv2.imdecode(src, 1)
                src = np.rot90(src, 3)
                self.back_up_dq.append(src)
            except IndexError as e:
                # 向备份Q中放置过快,超过摄像头读取速度，需要等待一帧时间
                time.sleep(2 / FpsMax)
        # 找到结束点后再继续保存最多30张:
        number = self.end_number + 1
        for i in range(40):
            try:
                src = self.back_up_dq.popleft()
                picture_save = cv2.resize(src, dsize=(0, 0), fx=0.7, fy=0.7)
                if self.draw_rec:
                    number += 1
                    self.draw_line_in_pic(number=number, picture=picture_save)
                    self.draw_rec = False
                    continue
                cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), picture_save)
                number += 1
            except IndexError as e:
                print(repr(e))
                return 0
        self.back_up_dq.clear()
        return 0
