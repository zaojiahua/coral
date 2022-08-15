import os
import platform
import time
from collections import deque
import traceback
import gc

import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

from app.config.ip import HOST_IP
from app.execption.outer.error_code.imgtool import VideoStartPointNotFound, \
    VideoEndPointNotFound, FpsLostWrongValue, PerformanceNotStart
from app.v1.Cuttle.basic.operator.hand_operate import creat_sensor_obj, close_all_sensor_connect
from app.v1.Cuttle.basic.setting import FpsMax, CameraMax, set_global_value, \
    CAMERA_IN_LOOP, SENSOR, sensor_serial_obj_dict, get_global_value, camera_dq_dict
from app.config.setting import CORAL_TYPE
from app.v1.Cuttle.basic.operator.camera_operator import get_camera_ids

sp = '/' if platform.system() == 'Linux' else '\\'
EXTRA_PIC_NUMBER = 40


class PerformanceCenter(object):
    # dq存储起始点前到终止点后的每一帧图片
    inner_back_up_dq = deque(maxlen=CameraMax)

    # 这部分是性能测试的中心对象，性能测试主要测试启动点 和终止点两个点位，并根据拍照频率计算实际时间
    # 终止点比较简单，但是启动点由于现有机械臂无法确认到具体点压的时间，只能通过机械臂遮挡关键位置时间+补偿时间（机械臂下落按压时间）计算得到
    # 补偿时间又区分出多种情况，点击普通滑动 和用力滑动，第一接触点位置位于屏幕x方向的位置（摄像头角度），需要分别计算补偿的帧数。
    def __new__(cls, *args, **kwargs):
        # 单例
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, device_id, icon_area, refer_im_path, scope, threshold, work_path: str, **kwargs):
        self.device_id = device_id
        self.result = {}
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

    @property
    def back_up_dq(self):
        if len(get_camera_ids()) > 1:
            return self.inner_back_up_dq
        else:
            # 其他类型的柜子就一个相机
            for camera_key in camera_dq_dict:
                return camera_dq_dict.get(camera_key)

    def get_back_up_image(self, image):
        if len(get_camera_ids()) > 1:
            return image
        else:
            return np.rot90(self.get_roi(image), 3)

    # 这的逻辑和camera operator中有些重复
    def get_roi(self, src):
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self.device_id)
        return src[int(device_obj.y1) - int(device_obj.roi_y1): int(device_obj.y2) - int(device_obj.roi_y1),
                   int(device_obj.x1) - int(device_obj.roi_x1): int(device_obj.x2) - int(device_obj.roi_x1)]

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
        number = 0
        self.start_number = 0

        def camera_loop():
            set_global_value(CAMERA_IN_LOOP, True)
            executer = ThreadPoolExecutor()
            self.move_src_future = executer.submit(self.move_src_to_backup)

        # 使用传感器获取点击的起始点，精确度更高一些
        if SENSOR:
            begin_time = time.time()
            find_begin_point = False
            max_force = 0
            v_index = None
            while self.loop_flag:
                # 不管左还是右，全部判断压力值即可
                for index, sensor_key in enumerate(sensor_serial_obj_dict.keys()):
                    if sensor_serial_obj_dict[sensor_key] is None:
                        sensor_com = sensor_key.split(self.device_id)[1]
                        sensor_serial_obj_dict[sensor_key] = creat_sensor_obj(sensor_com)
                    # 找到到底是哪个机械臂在点击
                    if v_index is not None and index != v_index:
                        continue

                    # 力是一个从小变大，又变小的过程
                    cur_force = sensor_serial_obj_dict[sensor_key].query_sensor_value()
                    if cur_force < max_force:
                        camera_loop()
                        find_begin_point = True
                        self.bias = 0
                        self.start_timestamp = time.time() * 1000
                        print('找到了起始点', self.start_timestamp)
                        break
                    elif cur_force > max_force:
                        max_force = cur_force
                        v_index = index

                if find_begin_point:
                    close_all_sensor_connect()
                    break
                elif (CameraMax / FpsMax) < time.time() - begin_time:
                    close_all_sensor_connect()
                    raise VideoStartPointNotFound
            close_all_sensor_connect()
        else:
            # 使用图像识别的方法计算起始点
            use_icon_scope = True if judge_function.__name__ == "_black_field" else False
            pic2 = self.judge_icon if judge_function.__name__ in ("_icon_find", "_black_field") else None

            camera_loop()

            while self.loop_flag:
                # 裁剪图片获取当前和下两张
                # start点的确认主要就是判定是否特定位置全部变成了黑色，既_black_field方法 （主要）/丢帧检测时是判定区域内有无变化（稀有）
                # 这部分如果是判定是否变成黑色（黑色就是机械臂刚要点下的时候，挡住图标所以黑色），其实只用到当前图，下两张没有使用
                picture, next_picture, third_pic, timestamp = self.picture_prepare(number,
                                                                                   use_icon_scope=use_icon_scope)
                if picture is None:
                    print('图片不够，start loop')
                    self.start_end_loop_not_found(VideoStartPointNotFound())

                number += 1
                # judge_function 返回True时 即发现了起始点
                if judge_function(picture, (pic2 if pic2 is not None else next_picture), third_pic, self.threshold):
                    # 这块的bias就是人工补偿的固定值，大致等于机械臂下压时间
                    self.bias = self.kwargs.get("bias") or 0
                    # 减一张得到起始点
                    self.start_number = number - 1
                    self.start_timestamp = timestamp
                    print(f"发现了起始点 :{number - 1} start number:{self.start_number}", '!' * 10)
                    if judge_function.__name__ == "_black_field":
                        # 除了查询丢帧情况，都要计算bias，既补偿的帧数，这部分是根据第一点击点的x位置，给一个线性的补偿（在上面固定下压时间的基础上）。
                        # 因为视角不同，摄像头在中间，看右侧的遮挡会偏早（所以要多加大bias），左侧的遮挡会偏晚（少加bias）
                        # 后续可以考虑优化成多项式
                        self.bias = self.bias + int((self.icon_scope[0] + self.icon_scope[2]) // (50 / FpsMax))
                    break
                elif number >= CameraMax / 2:
                    # 很久都没找到起始点的情况下，停止复制图片，清空back_up_dq，抛异常
                    self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                    self.start_end_loop_not_found(VideoStartPointNotFound())
                del picture

        # 如果能走到这里，代表发现了起始点，该unit结束，但是依然在获取图片
        return 0

    def start_end_loop_not_found(self, exp=VideoEndPointNotFound()):
        set_global_value(CAMERA_IN_LOOP, False)
        # result数据的写入 只有在end的时候是有效的
        self.result['url_prefix'] = "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path
        self.result['time_per_unit'] = round(1 / FpsMax, 4)
        if 'picture_count' not in self.result:
            if len(self.back_up_dq) > 1:
                self.result['picture_count'] = len(self.back_up_dq) - 1
            else:
                picture_count = len([lists for lists in os.listdir(self.work_path)
                                     if os.path.isfile(os.path.join(self.work_path, lists))]) - 1
                if picture_count > 0:
                    self.result['picture_count'] = picture_count
        # 判断取图的线程是否完全终止
        if hasattr(self, 'move_src_future'):
            for _ in as_completed([self.move_src_future]):
                print('move src 线程结束')
        self.back_up_clear()
        print('清空 back up dq 队列。。。。')
        raise exp

    def end_loop(self, judge_function):
        # 计算终止点的方法
        if not hasattr(self, "start_number") or not hasattr(self, "bias"):
            # 计算终止点前一定要保证已经有了起始点，不可以单独调用或在计算起始点结果负值时调用。
            self.start_end_loop_not_found(VideoStartPointNotFound())
        # 如果使用压力传感器，有可能里边还没有图片，所以选择等待一段时间
        if SENSOR:
            # 这里需要至少等待1s，因为1s以后才开始合并图片
            time.sleep(2)
        if len(self.back_up_dq) == 0:
            self.start_end_loop_not_found(PerformanceNotStart())

        if SENSOR:
            number = 0
        else:
            number = self.start_number + 1
        print("end loop start... now number:", number, "bias:", self.bias)

        if self.bias > 0:
            for i in range(self.bias):
                # 对bias补偿的帧数，先只保存对应图片，不做结果判断，因为不可能在这个阶段出现终止点 主要是加快一些速度。
                # 这里必须调用，因为里边会保存图片
                picture, next_picture, _, _ = self.picture_prepare(number)
                if picture is None:
                    print('图片不够 bias')
                    self.start_end_loop_not_found()
                number += 1

        use_icon_scope = True if judge_function.__name__ == "_is_blank" else False

        while self.loop_flag:
            # 这个地方写了两遍不是bug，是特意的，一次取了两张
            # 主要是找终止点需要抵抗明暗变化，计算消耗有点大，现在其实是跳着看终止点，一次过两张，能节约好多时间，让设备看起来没有等待很久很久
            # 准确度上就是有50%概率晚一帧，不过在240帧水平上，1帧误差可以接受
            # 这部分我们自己知道就好，千万别给客户解释出去了。
            picture, next_picture, third_pic, timestamp = self.picture_prepare(number, use_icon_scope)
            if picture is None:
                print('图片不够 loop 2')
                self.result = {'picture_count': number - 1, "start_point": self.start_number + self.bias}
                self.start_end_loop_not_found()
            number += 2

            if judge_function.__name__ in ["_icon_find", "_icon_find_template_match"]:
                # 判定终止图标出现只看标准图标和前后两张
                pic2 = self.judge_icon
                third_pic = next_picture
            else:
                # 判定区域是否有变化要一次看前后三张
                pic2 = next_picture
                third_pic = third_pic

            if judge_function(picture, pic2, third_pic, self.threshold):
                print(f"发现了终点: {number} bias：", self.bias)

                # 保留1s的图片
                if len(self.back_up_dq) < number + 1 * FpsMax:
                    # 实际帧率达不到，所以按照帧率缩小3倍算，这样基本足够了
                    time.sleep(1)

                set_global_value(CAMERA_IN_LOOP, False)
                if judge_function.__name__ not in ["_icon_find", "_icon_find_template_match"]:
                    # 判定区域是否有变化时，变化的帧是next_picture/third_pic，当前的picture是不能画框的，需要在另一个存图线程中画框
                    self.draw_rec = True
                    self.end_number = number
                else:
                    # 判定终止图标出现时，出现的帧就是当前picture，所以直接在这个图上画就可以
                    self.end_number = number - 1
                    self.draw_line_in_pic(number=self.end_number, picture=picture)

                # 找到终止点后，包装一个json格式，推到reef。
                job_duration = max(round((timestamp - self.start_timestamp) / 1000, 3), 0)
                if not SENSOR:
                    time_per_unit = round(job_duration / (self.end_number - self.start_number), 4)
                    self.start_number = int(self.start_number + self.bias)
                    # 实际的job_duration需要加上bias
                    job_duration = round(time_per_unit * (self.end_number - self.start_number), 3)
                else:
                    time_per_unit = round(job_duration / (self.end_number - self.start_number), 4)
                    # 在win上第一张图片有问题，可能是上次拍照留在相机内存中的图片，所以用第一张
                    self.start_number = 1

                self.result = {"start_point": self.start_number, "end_point": self.end_number,
                               "job_duration": job_duration,
                               "time_per_unit": time_per_unit,
                               "picture_count": self.end_number + EXTRA_PIC_NUMBER - 1,
                               "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                break
            # 最后一张在prepare的时候就拿不到了 一次拿俩张图
            elif number >= CameraMax - 2:
                job_duration = max(round((timestamp - self.start_timestamp) / 1000, 3), 0)
                if not SENSOR:
                    time_per_unit = round(job_duration / (number - self.start_number), 4)
                    job_duration = round(time_per_unit * (number - self.start_number - self.bias), 3)
                else:
                    time_per_unit = round(job_duration / (number - self.start_number), 4)
                    self.start_number = 1

                self.result = {"start_point": self.start_number + self.bias, "end_point": number,
                               "job_duration": job_duration,
                               "time_per_unit": time_per_unit,
                               "picture_count": number,
                               "url_prefix": "http://" + HOST_IP + ":5000/pane/performance_picture/?path=" + self.work_path}
                self.tguard_picture_path = os.path.join(self.work_path, f"{number - 1}.jpg")
                print('结束点图片判断超出最大数量')
                self.start_end_loop_not_found()
            del picture, next_picture, third_pic
        # 判断取图的线程是否完全终止
        for _ in as_completed([self.move_src_future]):
            print('move src 线程结束')
        return 0

    def draw_line_in_pic(self, number, picture):
        # 在结尾图片上画上选框（可能是画图标，也可能是画判定选区）
        is_icon = not (self.icon_scope is None or len(self.icon_scope) < 1)
        scope = self.icon_scope if is_icon else self.scope
        h, w = picture.shape[:2] if not (is_icon and self.scope != [0, 0, 1, 1]) else self.get_back_up_image(self.back_up_dq[0]['image']).shape[:2]
        area = [int(i) if i > 0 else 0 for i in [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]] \
            if 0 < all(i <= 1 for i in scope) else [int(i) for i in scope]
        x1, y1 = area[:2]
        x4, y4 = area[2:]
        pic = picture.copy()
        if is_icon and self.scope != [0, 0, 1, 1]:  # 需要画的是图标，但是需要在已有选区（裁剪后）的图片上画，所以需要换算
            x1 = x1 - int(self.scope[0] * w)
            y1 = y1 - int(self.scope[1] * h)
            x4 = x4 - int(self.scope[0] * w)
            y4 = y4 - int(self.scope[1] * h)
        cv2.rectangle(pic, (x1, y1), (x4, y4), (0, 255, 0), 4)
        cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), pic)

    def test_fps_lost(self, judge_function):
        # 这个方法还没完全做好，这仅当个思路吧
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
        print('准备图片：', number)
        picture = None
        max_retry_time = 10
        while max_retry_time >= 0:
            if len(self.back_up_dq) > number + 2:
                try:
                    picture_info = self.back_up_dq[number]
                    timestamp = picture_info['host_timestamp']
                    picture = self.get_back_up_image(picture_info['image'])
                    pic_next = self.get_back_up_image(self.back_up_dq[number + 1]['image'])
                    pic_next_next = self.get_back_up_image(self.back_up_dq[number + 2]['image'])
                    break
                except IndexError as e:
                    print("error in picture_prepare", repr(e))
            time.sleep(0.2)
            max_retry_time -= 1

        if picture is not None:
            h, w = picture.shape[:2]
            scope = self.scope if use_icon_scope is False else self.icon_scope
            area = [int(i) if i > 0 else 0 for i in [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]] \
                if 0 < all(i <= 1 for i in scope) else [int(i) for i in scope]
            return [p[area[1]:area[3], area[0]:area[2]]
                    for p in [picture, pic_next, pic_next_next]] + [timestamp]
        else:
            return None, None, None, None

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

    def back_up_clear(self):
        while len(self.back_up_dq) > 0:
            image_info = self.back_up_dq.popleft()
            del image_info['image']
        self.back_up_dq.clear()
        gc.collect()
        print('清空 back up dq 队列。。。。')

    def move_src_to_backup(self):
        self.back_up_dq.clear()
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self.device_id)
        # 这里会阻塞，一直在获取图片
        try:
            device_obj.get_snapshot(image_path='', max_retry_time=1,
                                    timeout=10 * 60, back_up_dq=self.back_up_dq, modify_fps=True)
        except Exception as e:
            print(e)
            traceback.print_exc()
            print('获取图片的接口报错。。。。')

        # 有可能图片全部拿完了，但是还没来得及处理图片呢
        while get_global_value(CAMERA_IN_LOOP):
            time.sleep(0.5)

        # 性能测试结束的最后再保存图片，可以加快匹配目标查找的速度
        find_end = False
        if hasattr(self, 'end_number'):
            find_end = True

        end_number = self.end_number + 1 if find_end else len(self.back_up_dq)
        try:
            for cur_index in range(end_number):
                picture_save = cv2.resize(self.get_back_up_image(self.back_up_dq[cur_index]['image']), dsize=(0, 0), fx=0.7, fy=0.7)
                if find_end and hasattr(self, "draw_rec") and \
                        self.draw_rec and cur_index == (end_number - 1):
                    # 这块就是做判断画面在动的时候，最后在临界帧画框
                    self.draw_line_in_pic(number=cur_index, picture=picture_save)
                    self.draw_rec = False
                else:
                    # 已经在结束点画了图
                    if cur_index != (end_number - 1):
                        cv2.imwrite(os.path.join(self.work_path, f"{cur_index}.jpg"), picture_save)
        except Exception as e:
            print(e)
            traceback.print_exc()

        # 找到结束点后再继续保存最多40张:
        if not find_end:
            self.back_up_clear()
            return 0

        number = self.end_number + 1
        # 额外再保留1s的图片
        for i in range(1 * FpsMax):
            try:
                src = self.get_back_up_image(self.back_up_dq[number]['image'])
                picture_save = cv2.resize(src, dsize=(0, 0), fx=0.7, fy=0.7)
                cv2.imwrite(os.path.join(self.work_path, f"{number}.jpg"), picture_save)
                number += 1
            except Exception as e:
                traceback.print_exc()
                self.back_up_clear()
                return 0

        # 销毁
        self.back_up_clear()
        print('move src to back up 正常结束')
