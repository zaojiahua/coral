import collections
import math
import os
import platform
import time
from collections import deque
import traceback
import gc

import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

from app.execption.outer.error_code.imgtool import VideoStartPointNotFound, \
    VideoEndPointNotFound, FpsLostWrongValue, PerformanceNotStart
from app.v1.Cuttle.basic.operator.hand_operate import creat_sensor_obj, close_all_sensor_connect
from app.v1.Cuttle.basic.setting import FpsMax, CameraMax, set_global_value, \
    CAMERA_IN_LOOP, sensor_serial_obj_dict, get_global_value, camera_dq_dict, CLICK_TIME
from app.v1.Cuttle.basic.operator.camera_operator import get_camera_ids
from app.config.setting import CORAL_TYPE
from redis_init import redis_client

sp = '/' if platform.system() == 'Linux' else '\\'
EXTRA_PIC_NUMBER = 40


class PerformanceCenter(object):
    # dq存储起始点前到终止点后的每一帧图片
    inner_back_up_dq = deque(maxlen=CameraMax)
    # 0: _black_field 1: 按下压感 2: 抬起压感 3: 图标膨胀
    start_method = 0
    start_area = None
    start_number = 0
    start_timestamp = 0
    # 终点相关
    end_method = 0
    end_number = 0
    end_area = None
    # 压感相关
    max_force = 0
    sensor_index = None
    force_dict = {}

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
        # 使用黑色区域时，icon_scope为icon实际出现在snap图中的位置，使用icon surf时icon_scope为编辑时出现在refer图中的位置
        # 使用选区变化/不变时 icon_scope 为None
        # icon 和scope 这里都是相对的坐标
        self.icon_scope = icon_area[0] if isinstance(icon_area, list) else None
        self.judge_icon = self.get_icon(refer_im_path)

        # 记录用户框选的图标原始区域
        if 'start_template_area' in kwargs:
            self.start_template_area = kwargs.get('start_template_area')[0]
            self.start_template_icon = self.get_icon(refer_im_path, self.start_template_area)

        self.scope = scope
        self.threshold = threshold
        self.move_flag = True
        self.loop_flag = True
        work_path = os.path.join(sp.join(os.path.dirname(work_path).split(sp)[:-1]), "performance") + sp
        if not os.path.exists(work_path):
            os.makedirs(work_path)
        self.work_path = work_path
        self.kwargs = kwargs
        self.set_fps = kwargs.get('set_fps', FpsMax)
        self.set_shot_time = kwargs.get('set_shot_time', CameraMax / FpsMax)
        # 图片保存的路径是固定的
        self.result = {'url_prefix': "path=" + self.work_path, 'frame_data': []}
        # 记录丢帧检测的所有组数
        self.groups = []

    @property
    def back_up_dq(self):
        return self.inner_back_up_dq

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

    def start_judge_function(self, picture, threshold, number=None, timestamp=None, next_pic=None):
        is_find = False
        if self.start_method == 0:
            # 传过来的图片不知为何，有可能是空的
            if picture is not None:
                is_find = self._black_field(picture, threshold)
                if is_find and timestamp is not None:
                    self.start_number = number
                    self.start_timestamp = timestamp
        elif self.start_method == 1:
            is_find = self.sensor_press_down()
        elif self.start_method == 2:
            is_find = self.sensor_press_down(up=True)
        elif self.start_method == 3:
            is_find = self.picture_changed(picture, next_pic, threshold)
            if is_find and timestamp is not None:
                self.start_number = number
                self.start_timestamp = timestamp
        elif self.start_method == 4:
            click_time = redis_client.get(CLICK_TIME)
            if click_time is not None and click_time != '0':
                if time.time() >= float(click_time):
                    # 转换为毫秒
                    self.start_timestamp = float(click_time) * 1000
                    self.start_number, _ = self.get_picture_number(self.start_timestamp)
                    is_find = True
            time.sleep(0.1)
        elif self.start_method == 5:
            min_value, min_loc = self.template_match(picture)

            picture_info = self.back_up_dq[number]
            # 记录相关信息，debug的时候不需要再获取信息了
            picture_info['min_value'] = str(round(1 - min_value, 2))
            picture_info['min_loc'] = min_loc

            if min_value < 1 - threshold:
                self.start_number = number
                self.start_timestamp = timestamp
                is_find = True
        else:
            is_find = False
        return is_find

    def template_match(self, picture):
        target = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(self.start_template_icon, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(target, template, cv2.TM_SQDIFF_NORMED)
        min_val, _, min_loc, _ = cv2.minMaxLoc(result)

        return min_val, min_loc

    # 判断图片是否发生了变化
    @staticmethod
    def picture_changed(picture, next_pic, threshold):
        difference_threshold = 25
        difference = np.absolute(np.subtract(picture, next_pic))
        # result结果代表相似性
        result = np.count_nonzero(difference < difference_threshold)
        result2 = np.count_nonzero(difference > (255 - difference_threshold))
        standard = picture.shape[0] * picture.shape[1] * picture.shape[2]
        match_ratio = ((result + result2) / standard)
        return match_ratio < threshold

    @staticmethod
    def black_field(picture):
        try:
            picture = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        except Exception as e:
            print('black field 出错', e, picture.shape)
        ret, picture = cv2.threshold(picture, 40, 255, cv2.THRESH_BINARY)
        result = np.count_nonzero(picture < 40)
        standard = picture.shape[0] * picture.shape[1]
        match_ratio = round(result / standard + 0.01, 2)
        return picture, match_ratio

    def _black_field(self, picture, threshold):
        _, match_ratio = self.black_field(picture)
        return match_ratio > threshold

    # 传感器获取按压的起始点
    def sensor_press_down(self, up=False):
        find_begin_point = False

        # 不管左还是右，全部判断压力值即可
        for index, sensor_key in enumerate(sensor_serial_obj_dict.keys()):
            if sensor_serial_obj_dict[sensor_key] is None:
                sensor_com = sensor_key.split(self.device_id)[1]
                sensor_serial_obj_dict[sensor_key] = creat_sensor_obj(sensor_com)
            # 找到到底是哪个机械臂在点击
            if self.sensor_index is not None and index != self.sensor_index:
                continue

            # 力是一个从小变大，又变小的过程
            cur_force = sensor_serial_obj_dict[sensor_key].query_sensor_value()
            force_time = round(time.time() * 1000)
            print('力值：', cur_force, str(force_time))

            # 同一个时间可能得到了很多不同的值
            if cur_force == 0.0:
                if cur_force not in self.force_dict[force_time]:
                    self.force_dict[force_time].append(cur_force)
            else:
                if len(self.force_dict[force_time]) == 0 or cur_force != self.force_dict[force_time][-1]:
                    self.force_dict[force_time].append(cur_force)

            if cur_force < self.max_force:
                # 抬起的起始点
                find_begin_point = True
                break
            elif cur_force > self.max_force:
                self.max_force = cur_force
                self.sensor_index = index
                # 按下的起始点
                if cur_force > 0 and not up:
                    find_begin_point = True
                    break

        if find_begin_point:
            self.start_timestamp = force_time
            print('找到了起始点', self.start_timestamp)
            self.start_number, _ = self.get_picture_number(self.start_timestamp)
            close_all_sensor_connect()

        return find_begin_point

    def get_icon(self, refer_im_path, icon_scope=None):
        # 在使用黑色区域计算时，self.icon_scope为实际出现在snap图中的位置，此方法无意义
        # 在使用icon surf计算时，self.icon_scope为编辑时出现在refer图中的位置，此方拿到的是icon标准图
        if icon_scope is None:
            icon_scope = self.icon_scope
        if not all((refer_im_path, icon_scope)):
            return None

        picture = cv2.imread(refer_im_path)
        h, w = picture.shape[:2]
        area = [int(i) if i > 0 else 0 for i in
                [icon_scope[0] * w, icon_scope[1] * h, icon_scope[2] * w, icon_scope[3] * h]]
        return picture[area[1]:area[3], area[0]:area[2]]

    def camera_loop(self):
        set_global_value(CAMERA_IN_LOOP, True)
        executer = ThreadPoolExecutor()
        self.move_src_future = executer.submit(self.move_src_to_backup)

    def start_loop(self, start_method=0):
        number = 0
        self.start_method = start_method
        self.start_number = 0
        self.end_number = 0
        self.max_force = 0
        self.sensor_index = None
        self.start_timestamp = 0
        self.force_dict = collections.defaultdict(list)

        self.camera_loop()

        # 感兴趣的区域只需要计算一次即可，因为每张图片大小都是一样的，感兴趣的区域也没有变过
        area = self.get_area(self.scope if self.start_method != 0 else self.icon_scope)
        self.start_area = area

        while self.loop_flag:
            # 裁剪图片获取当前和下两张
            # start点的确认主要就是判定是否特定位置全部变成了黑色，既_black_field方法 （主要）/丢帧检测时是判定区域内有无变化（稀有）
            # 这部分如果是判定是否变成黑色（黑色就是机械臂刚要点下的时候，挡住图标所以黑色），其实只用到当前图，下两张没有使用
            if self.start_method in [0, 3, 5]:
                picture, next_pic, __, timestamp = self.picture_prepare(number, area)
                if picture is None:
                    print('图片不够，start loop')
                    self.start_end_loop_not_found(VideoStartPointNotFound())
            else:
                # 传感器判断起点不需要图片
                picture = None
                timestamp = None
                next_pic = None

            # judge_function 返回True时 即发现了起始点
            if self.start_judge_function(picture, self.threshold, number, timestamp, next_pic):
                print(f"循环到的次数 :{number} 发现了起始点 :{self.start_number}", '!' * 10)
                break
            elif number >= CameraMax / 2:
                print(f'找不到起点了，开始退出。。。{number}')
                # 很久都没找到起始点的情况下，停止复制图片，清空back_up_dq，抛异常
                self.start_end_loop_not_found(VideoStartPointNotFound())
            number += 1
            del picture

        # 如果能走到这里，代表发现了起始点，该unit结束，但是依然在获取图片
        return 0

    def start_end_loop_not_found(self, exp=None):
        set_global_value(CAMERA_IN_LOOP, False)

        if 'time_per_unit' not in self.result or self.start_method in [1, 2]:
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
        raise exp or VideoEndPointNotFound()

    # 终点的判断方法
    def end_judge_function(self, picture, threshold, number=None, timestamp=None):
        if self.end_method == 0:
            pass
        elif self.end_method == 1:
            pass
        elif self.end_method == 2:
            pass
        else:
            pass

    def end_loop(self, judge_function):
        # 找到起点的时候，一定有有效的起始时间
        if not hasattr(self, "start_timestamp") or not self.start_timestamp:
            # 计算终止点前一定要保证已经有了起始点，不可以单独调用或在计算起始点结果负值时调用。
            self.start_end_loop_not_found(VideoStartPointNotFound())

        number = self.start_number + 1
        print("end loop start... now number:", number)

        picture_not_enough = False
        timestamp_dict = {}
        if self.start_method == 0:
            while True:
                picture, next_picture, third_pic, timestamp = self.picture_prepare(number, self.start_area)
                timestamp_dict[number] = timestamp
                # 从start到bias这段时间，应该都是属于满足条件的区间
                if not self.start_judge_function(picture, self.threshold):
                    self.bias = number
                    break
                if picture is None:
                    picture_not_enough = True
                    break
                number += 1
        else:
            self.bias = self.start_number

        # 重置number，比如用力滑动的时候，屏幕变化很快，或者响应非常快速的设备，而我们的帧率又达不到的时候
        number = math.ceil((self.start_number + self.bias) / 2)
        print("reset number, now number:", number)

        # 这里重新设置一下start_number，因为终点不一定可以找到，start_number的值必须正确了
        if self.start_method == 0:
            self.start_number = math.ceil(int(self.start_number + self.bias) / 2)
            self.start_timestamp = timestamp_dict[self.start_number]

            # 在寻找bias的时候，如果图片不够，报错
            if picture_not_enough:
                self.start_end_loop_not_found()

        use_icon_scope = True if judge_function.__name__ == "_is_blank" else False
        area = self.get_area(self.scope if use_icon_scope is False else self.icon_scope)

        while self.loop_flag:
            # 这个地方写了两遍不是bug，是特意的，一次取了两张
            # 主要是找终止点需要抵抗明暗变化，计算消耗有点大，现在其实是跳着看终止点，一次过两张，能节约好多时间，让设备看起来没有等待很久很久
            # 准确度上就是有50%概率晚一帧，不过在240帧水平上，1帧误差可以接受
            # 这部分我们自己知道就好，千万别给客户解释出去了。
            picture, next_picture, third_pic, timestamp = self.picture_prepare(number, area)
            if picture is None or number >= CameraMax - 2:
                print('图片不够或者已经达到了取图的最大值')
                # 用上一次的图片时间，计算time per unit
                _, __, ___, pre_timestamp = self.picture_prepare(number - 2, area)
                job_duration = max(round((pre_timestamp - self.start_timestamp) / 1000, 3), 0)
                time_per_unit = round(job_duration / (number - 2 - self.start_number), 4)
                self.result['picture_count'] = number - 1
                self.result['start_point'] = self.start_number
                self.result['time_per_unit'] = time_per_unit
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
                print(f"发现了终点: {number} bias：", self.bias, timestamp)

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

                # 找到终止点后，包装一个json格式，推到reef
                job_duration = max(round((timestamp - self.start_timestamp) / 1000, 3), 0)
                time_per_unit = round(job_duration / (self.end_number - self.start_number), 4)
                picture_count = int(self.end_number + FpsMax - 1)

                self.result['start_point'] = self.start_number
                self.result['end_point'] = self.end_number
                self.result['job_duration'] = job_duration
                self.result['time_per_unit'] = time_per_unit
                self.result['picture_count'] = len(self.back_up_dq) \
                    if len(self.back_up_dq) < picture_count else picture_count
                break
        # 判断取图的线程是否完全终止
        for _ in as_completed([self.move_src_future]):
            print('move src 线程结束')
        return 0

    def draw_line_in_pic(self, number, picture):
        # 在结尾图片上画上选框（可能是画图标，也可能是画判定选区）
        is_icon = not (self.icon_scope is None or len(self.icon_scope) < 1)
        scope = self.icon_scope if is_icon else self.scope
        h, w = picture.shape[:2] if not (is_icon and self.scope != [0, 0, 1, 1]) else self.get_back_up_image(self.back_up_dq[0]['image']).shape[:2]
        area = self.get_area(scope, h, w)
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

    def fps_lost(self):
        # 必须找到一个变化的区间才能继续往下判断
        if not self.start_number:
            self.start_end_loop_not_found(VideoStartPointNotFound())

        number = self.start_number
        print("end loop start... now number:", number)

        # 感兴趣的区域只需要计算一次即可，因为每张图片大小都是一样的，感兴趣的区域也没有变过
        self.end_area = self.get_area(self.scope)
        # 一组的第一张图片
        group_start_pic = None
        # 记录所有的组数
        self.groups = []
        current_group = {}

        while self.loop_flag:
            number += 1
            picture, _, _, timestamp = self.picture_prepare(number, self.end_area)
            if picture is None or number >= CameraMax - 1:
                print('图片不够或已经达到了取图的最大值')
                self.result['picture_count'] = number - 1
                self.result['start_point'] = self.start_number
                self.start_end_loop_not_found()

            if group_start_pic is None:
                group_start_pic = picture
                current_group['start_number'] = number
                current_group['start_time'] = timestamp
                continue
            else:
                if self.picture_changed(group_start_pic, picture, self.threshold):
                    # 记录旧的组数
                    current_group['end_number'] = number - 1
                    current_group['end_time'] = self.back_up_dq[number - 1]['host_timestamp']
                    self.groups.append(current_group)
                    print('产生出来一组帧：', current_group)
                    # 产生新的一组
                    current_group = {'start_number': number, 'start_time': timestamp}
                    group_start_pic = picture
                else:
                    # 连续多张图片没有变化就认为找到了终点 能检测到的最低帧率是10
                    if current_group['start_number'] < number - FpsMax / 10:
                        print('找到终点了', number)
                        self.end_number = number
                        # 保留1s的图片 方便用户查看
                        if len(self.back_up_dq) < number + 1 * FpsMax:
                            time.sleep(1)

                        set_global_value(CAMERA_IN_LOOP, False)
                        picture_count = int(self.end_number + FpsMax - 1)
                        self.result['start_point'] = self.start_number
                        self.result['end_point'] = self.end_number
                        self.result['picture_count'] = len(self.back_up_dq) \
                            if len(self.back_up_dq) < picture_count else picture_count
                        break
        # 判断取图的线程是否完全终止
        for _ in as_completed([self.move_src_future]):
            print('move src 线程结束')
        return 0

    def get_area(self, scope, h=None, w=None):
        if h is None and w is None:
            # 得保证至少有一张图片
            max_times = 10
            while True:
                try:
                    picture_info = self.back_up_dq[0]
                    picture = self.get_back_up_image(picture_info['image'])
                    h, w = picture.shape[:2]
                    break
                except IndexError:
                    time.sleep(0.5)
                    max_times -= 1
                    if max_times <= 0:
                        break

            if max_times <= 0:
                print('相机中没有图片。。。。。。', len(self.back_up_dq))

        area = [int(i) if i > 0 else 0 for i in [scope[0] * w, scope[1] * h, scope[2] * w, scope[3] * h]] \
            if 0 < all(i <= 1 for i in scope) else [int(i) for i in scope]

        return area

    def picture_prepare(self, number, area):
        # use_icon_scope为true时裁剪snap图中真实icon出现的位置
        # use_icon_scope为false时裁剪snap图中refer中标记的configArea选区大致范围
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
            print('准备图片：', number, ' 帧号：', picture_info['frame_num'])
            return [p[area[1]:area[3], area[0]:area[2]] for p in [picture, pic_next, pic_next_next]] + [timestamp]
        else:
            return None, None, None, None

    def back_up_clear(self):
        while len(self.back_up_dq) > 0:
            image_info = self.back_up_dq.popleft()
            del image_info['image']
        self.back_up_dq.clear()
        gc.collect()
        # 单例模式，这里对变量进行清空，无论成功还是失败，肯定会调用这里
        self.start_number = 0
        self.start_timestamp = 0
        print('清空 back up dq 队列。。。。')

    def move_src_to_backup(self):
        self.back_up_dq.clear()
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self.device_id)
        # 这里会阻塞，一直在获取图片
        try:
            snapshot_result = device_obj.get_snapshot(image_path='', max_retry_time=1, timeout=10 * 60,
                                                      back_up_dq=self.back_up_dq, modify_fps=True, set_fps=self.set_fps,
                                                      set_shot_time=self.set_shot_time)
            print('snap shot返回值：', snapshot_result)
        except Exception as e:
            print(e)
            traceback.print_exc()
            print('获取图片的接口报错。。。。')

        # 有可能图片全部拿完了，但是还没来得及处理图片呢
        while get_global_value(CAMERA_IN_LOOP):
            time.sleep(0.5)

        # 性能测试结束的最后再保存图片，可以加快匹配目标查找的速度
        find_end = False
        if hasattr(self, 'end_number') and self.end_number:
            find_end = True

        # 如果是双摄，图片没有来得及合并，找的起点图片偏小，所以重新设置一下起点的值
        if self.start_method in [1, 2, 4]:
            if 'start_point' in self.result:
                self.start_number, host_timestamp = self.get_picture_number(self.start_timestamp)
                self.bias = self.start_number
                print('在最后重新设置起始点：', self.start_number)
                self.result['start_point'] = self.start_number
                if find_end:
                    # 修改time_per_unit，便于前端计算
                    end_host_timestamp = self.back_up_dq[self.end_number]['host_timestamp']
                    job_duration = max(round((end_host_timestamp - host_timestamp) / 1000, 3), 0)
                    time_per_unit = round(job_duration / (self.end_number - self.start_number), 4)
                    self.result['time_per_unit'] = time_per_unit

        end_number = self.end_number + 1 if find_end else len(self.back_up_dq)
        print('保存图片时候的end number', end_number, '*' * 10)

        try:
            for cur_index in range(end_number):
                picture_info = self.back_up_dq[cur_index]
                picture = self.get_back_up_image(picture_info['image'])
                pic_h, pic_w, _ = picture.shape

                # 在这个地方画上要找的起始点，调试的时候使用
                if not hasattr(self, 'start_number') or self.start_number == 0\
                        or not hasattr(self, 'bias') or (hasattr(self, 'bias') and cur_index <= self.bias):
                    if self.start_method == 0:
                        picture_area = picture[self.start_area[1]:self.start_area[3],
                                               self.start_area[0]:self.start_area[2]]
                        picture_area, match_ratio = self.black_field(picture_area)
                        picture[self.start_area[1]:self.start_area[3],
                                self.start_area[0]:self.start_area[2]] = cv2.cvtColor(picture_area, cv2.COLOR_GRAY2BGR)
                        picture = cv2.rectangle(picture.copy(), (self.start_area[0], self.start_area[1]),
                                                (self.start_area[2], self.start_area[3]), (0, 0, 255), 2)
                        picture = cv2.putText(picture.copy(), str(match_ratio), (self.start_area[2] + 10, self.start_area[1] + 10),
                                              cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 3)
                        picture_info['parameter'] = str(match_ratio)
                    elif self.start_method in [1, 2]:
                        host_timestamp = picture_info['host_timestamp']
                        force, timestamp = self.get_force(host_timestamp)
                        timestamp = time.strftime(
                            "%H:%M:%S", time.localtime(timestamp / 1000)) + '.' + str(timestamp)[-3:]
                        host_timestamp = time.strftime(
                            "%H:%M:%S", time.localtime(host_timestamp / 1000)) + '.' + str(host_timestamp)[-3:]
                        print('force:', force)
                        picture = cv2.putText(picture.copy(), f'snap time: {host_timestamp}',
                                              (20, 200), cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 2)
                        picture = cv2.putText(picture.copy(), f'force time: {timestamp}',
                                              (20, 300), cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 2)
                        step = 5
                        for force_index in range(0, len(force), step):
                            picture = cv2.putText(picture.copy(),
                                                  f'force: {force[force_index: force_index + step]}',
                                                  (20, 400 + force_index * 20),
                                                  cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 2)
                    elif self.start_method in [5]:
                        h, w = self.start_template_icon.shape[:2]
                        if 'min_loc' in picture_info:
                            min_loc = picture_info['min_loc']
                            min_value = picture_info['min_value']
                            right_bottom = (min_loc[0] + w, min_loc[1] + h)
                            picture = cv2.putText(picture.copy(),
                                                  f'{min_value}',
                                                  (int(min_loc[0] + w / 2), int(min_loc[1] + h / 2)),
                                                  cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 2)
                            picture = cv2.rectangle(picture.copy(), min_loc, right_bottom, (0, 0, 255), 2)
                            picture_info['parameter'] = min_value

                # 对丢帧检测的结果进行绘图
                if self.start_method == 3:
                    picture = cv2.rectangle(picture.copy(), (self.end_area[0], self.end_area[1]),
                                            (self.end_area[2], self.end_area[3]), (0, 255, 0), 4)
                    group_info = self.get_picture_group(cur_index)
                    # 记录分组信息
                    if group_info is not None:
                        try:
                            fps = round(1 / (group_info['end_time'] - group_info['start_time']) * 1000, 1)
                        except ZeroDivisionError:
                            fps = FpsMax
                        # print(fps, group_info)
                        picture = cv2.putText(picture.copy(), f'fps: {fps}', (self.end_area[0], self.end_area[1] - 10),
                                              cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 2)

                # picture_save = cv2.resize(picture, dsize=(0, 0), fx=0.7, fy=0.7)
                picture_save = picture
                if find_end and hasattr(self, "draw_rec") and \
                        self.draw_rec and cur_index == (end_number - 1):
                    # 这块就是做判断画面在动的时候，最后在临界帧画框
                    self.draw_line_in_pic(number=cur_index, picture=picture_save)
                    self.draw_rec = False
                else:
                    # 已经在结束点画了图
                    if cur_index != (end_number - 1) or not find_end:
                        cv2.imwrite(os.path.join(self.work_path, f"{cur_index}.jpg"), picture_save)
        except Exception as e:
            print(e)
            traceback.print_exc()

        try:
            self.result['start_method'] = self.start_method + 1
            self.result['end_method'] = self.end_method + 1
            self.result['set_fps'] = self.set_fps
            self.result['set_shot_time'] = self.set_shot_time
            # 保存性能测试过程中的相关数据，推送到服务器，方便前端展示
            for frame_num in range(min(len(self.back_up_dq), end_number + int(1 * FpsMax))):
                frame_data = {}
                picture_info = self.back_up_dq[frame_num]
                frame_data['frame_num'] = frame_num
                frame_data['timestamp'] = picture_info['host_timestamp']
                frame_data['parameter'] = picture_info.get('parameter')
                try:
                    frame_data['frame_duration'] = self.back_up_dq[frame_num + 1]['host_timestamp'] - \
                                                   picture_info['host_timestamp']
                except IndexError:
                    pass
                self.result['frame_data'].append(frame_data)
            if len(self.result['frame_data']) > 0:
                self.result['fps'] = round(len(self.result['frame_data']) /
                                              ((self.result['frame_data'][-1]['timestamp'] -
                                               self.result['frame_data'][0]['timestamp']) / 1000), 0)
        except Exception as e:
            print(e)
            traceback.print_exc()

        # 找到结束点后再继续保存最多40张:
        if not find_end:
            self.back_up_clear()
            return 0

        number = self.end_number + 1
        # 额外再保留1s的图片
        for i in range(int(1 * FpsMax)):
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

    # 获取指定时间点，传感器的力值
    def get_force(self, host_timestamp):
        min_value = None
        target_timestamp = 0
        # key是无序的，所以需要比较完所有的值
        for timestamp in self.force_dict.keys():
            distance = abs(host_timestamp - timestamp)
            if min_value is None or distance < min_value:
                min_value = distance
                target_timestamp = timestamp

        return self.force_dict[target_timestamp], target_timestamp

    # 根据时间，获取距离该时间最近的一张图片
    def get_picture_number(self, timestamp):
        min_value = None
        host_timestamp = None
        pic_number = len(self.back_up_dq)
        for picture_index, picture_info in enumerate(self.back_up_dq):
            host_timestamp = picture_info['host_timestamp']
            distance = abs(host_timestamp - timestamp)
            # 这里必须写等于，怕相机获取到的俩张图时间一致
            if min_value is None or distance <= min_value:
                min_value = distance
            else:
                return picture_index, host_timestamp
        return pic_number - 1, host_timestamp

    # 获得当前图片对应的组数数据
    def get_picture_group(self, number):
        for group in self.groups:
            if group['start_number'] <= number <= group['end_number']:
                return group
