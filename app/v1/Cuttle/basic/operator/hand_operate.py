import math
import os
import re
import threading
import time
import traceback

import numpy as np

from app.config.setting import CORAL_TYPE, arm_com, arm_com_1
from app.config.url import phone_model_url
from app.execption.outer.error_code.hands import KeyPositionUsedBeforesSet, ChooseSerialObjFail, InvalidCoordinates, \
    RepeatTimeInvalid, TcabNotAllowExecThisUnit, CoordinatesNotReasonable
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.default_calculate import DefaultMixin
from app.v1.Cuttle.basic.hand_serial import HandSerial, controlUsbPower, SensorSerial
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.component.hand_component import read_wait_position, get_wait_position
from app.v1.Cuttle.basic.setting import HAND_MAX_Y, HAND_MAX_X, SWIPE_TIME, Z_START, Z_UP, MOVE_SPEED, \
    hand_serial_obj_dict, normal_result, trapezoid, arm_default, arm_move_position, rotate_hand_serial_obj_dict, \
    hand_origin_cmd_prefix, X_SIDE_KEY_OFFSET, \
    sensor_serial_obj_dict, PRESS_SIDE_KEY_SPEED, get_global_value, ARM_MOVE_REGION, DIFF_X, \
    ARM_COUNTER_PREFIX, ARM_RESET_THRESHOLD

from app.execption.outer.error_code.camera import CoordinateConvert
from redis_init import redis_client
from app.v1.Cuttle.basic.common_utli import reset_arm


def get_hand_serial_key(device_label, arm_com_id):
    return device_label + '@' + arm_com_id


def hand_init(arm_com_id, device_obj, **kwargs):
    # 龙门架机械臂初始化
    """
    1. 解锁机械臂，并将机械臂移动至Home位置
    2. 设置坐标模式为绝对值模式
    3. 设置HOME点为操作原点
    :return:
    """
    # 不同的机柜设置的待命位置不同，需要先从配置文件中读取当前的
    read_wait_position()
    obj_key = get_hand_serial_key(device_obj.pk, arm_com_id)
    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id=arm_com_id)
    hand_serial_obj_dict[obj_key] = hand_serial_obj
    wait_position = get_wait_position(arm_com_id)
    hand_reset_orders = [
        "$x \r\n",
        "$h \r\n",
        f"G92 X0Y0Z0 \r\n",
        "G90 \r\n",
        wait_position
    ]
    for orders in hand_reset_orders:
        hand_serial_obj.send_single_order(orders)
        hand_serial_obj.recv(buffer_size=64, is_init=True)
    return 0


# 当执行的指令条数达到一定的数目的时候，复位机械臂，并且重新开始计数
def hand_reset(target_device_label=None):
    for com_id in hand_serial_obj_dict.keys():
        # 查看当前机械臂已经执行了多少条指令了
        device_label, com_id = com_id.split('@')

        # 和指定设备关联的机械臂进行复位
        if target_device_label is not None:
            if device_label != target_device_label:
                continue

        counter = redis_client.get(f'{ARM_COUNTER_PREFIX}{com_id}')
        if int(counter) > ARM_RESET_THRESHOLD:
            # 复位机械臂，并且清空计数器
            print(f'{counter} 机械臂执行指令达到了{ARM_RESET_THRESHOLD}，开始复位')
            reset_arm(device_label, com_id)
            redis_client.set(f'{ARM_COUNTER_PREFIX}{com_id}', 0)


def rotate_hand_init(arm_com_id, device_obj, **kwargs):
    # 旋转机械臂初始化
    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id=arm_com_id)
    rotate_hand_serial_obj_dict[device_obj.pk] = hand_serial_obj
    hand_reset_orders = [
        "$G \r\n",
        "$x \r\n",
        "G92 X0Y0Z0F15000 \r\n",
        "G90 \r\n",
        arm_default
    ]
    for g_orders in hand_reset_orders:
        hand_serial_obj.send_single_order(g_orders)
        hand_serial_obj.recv(buffer_size=64, is_init=True)
    return 0


def creat_sensor_obj(arm_com_id):
    print("创建传感器对象，", arm_com_id)
    sensor_obj = SensorSerial(baud_rate=115200, timeout=2)
    sensor_obj.connect(arm_com_id)
    sensor_obj.send_read_order()
    return sensor_obj


def sensor_init(arm_com_id, device_obj, **kwargs):
    print('初始化传感器', arm_com_id, '&' * 10)
    sensor_obj = creat_sensor_obj(arm_com_id)
    sensor_obj.close()
    sensor_serial_obj_dict[device_obj.pk + arm_com_id] = None


def close_all_sensor_connect():
    print("关闭传感器连接....")
    for sensor_key, sensor_obj in sensor_serial_obj_dict.items():
        if isinstance(sensor_obj, SensorSerial):
            sensor_obj.close()
        sensor_serial_obj_dict[sensor_key] = None
    return 0


def pre_point(point, arm_num=0):
    """
    该函数用来对要点击的坐标进行预处理
    该函数默认所有机械臂使用同一个Z值
    比如：如果执行坐标的机械臂原点在左上角，其x,y为[x, -y]
         如果执行坐标的机械臂原点在右上角，其x,y为[-x, -y]
    point: [x, y]  --> 基于第三套坐标系(x,y > 0)
    arm_num: 定义主机械臂编号为0，机械臂原点在左上角，其x,y为[x, -y]
                副机械臂编号为1，机械臂原点在右上角，其x,y为[-x, -y]， 且 x 坐标为 -(MAX_X - point[0])

    """
    z_point = point[2] if len(point) == 3 else get_global_value('Z_DOWN')
    if arm_num == 0:
        return [point[0], -point[1], z_point]
    if arm_num == 1:
        if CORAL_TYPE == 5.3 or CORAL_TYPE == 5.5:
            z_point = point[2] if len(point) == 3 else get_global_value('Z_DOWN_1')
        if CORAL_TYPE == 5.5:
            x_point = -HAND_MAX_X + point[0]
            y_point = -point[1] + 9
        else:
            x_point = HAND_MAX_X - point[0]
            y_point = -point[1] + 1
        return [-x_point, y_point, z_point]
    raise ChooseSerialObjFail


def judge_start_x(start_x_point, device_level):
    arm_num = 0
    suffix_key = arm_com
    if CORAL_TYPE == 5.3 or CORAL_TYPE == 5.5:
        suffix_key = arm_com if start_x_point < ARM_MOVE_REGION[0] else arm_com_1
        arm_num = 0 if suffix_key == arm_com else 1
    exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(device_level, suffix_key))
    return exec_serial_obj, arm_num


def allot_serial_obj(func):
    # 该函数用来分配执行的机械臂对象
    def wrapper(self, axis, **kwargs):
        start_x_point = axis[0][0] if type(axis[0]) is list else axis[0]
        exec_serial_obj, arm_num = judge_start_x(start_x_point, self._model.pk)
        kwargs["exec_serial_obj"] = exec_serial_obj
        kwargs["arm_num"] = arm_num
        return func(self, axis, **kwargs)

    return wrapper


class HandHandler(Handler, DefaultMixin):
    before_match_rules = {
        # 用在执行之前，before_execute中针对不同方法正则替换其中的相对坐标到绝对坐标
        "input tap": "_relative_point",
        "input swipe": "_multi_swipe",
        "multi swipe": "_multi_swipe",
        "double_point": "_relative_double_point",
        "double hand zoom": "_relative_double_hand",
    }
    arm_exec_content_str = ["arm_back_home", "open_usb_power", "close_usb_power", "cal_swipe_speed",
                            "double_hand_swipe", "repeat_sliding", "record_repeat_count", "repeat_fast_sliding"]

    def __init__(self, *args, **kwargs):
        super(HandHandler, self).__init__(*args, **kwargs)
        self.double_hand_point = None
        self.ignore_reset = False
        self.performance_start_point = kwargs.get('performance_start_point')
        self.kwargs = kwargs
        self.repeat_count = 0
        self.repeat_click_dict = {}
        self.pix_points = None

    def before_execute(self):
        # 先转换相对坐标到绝对坐标
        for key, value in self.before_match_rules.items():
            if key in self.exec_content:
                getattr(self, value)()
                break
        # 根据adb指令中的关键词dispatch到对应机械臂方法,pix_points为adb模式下的截图中的像素坐标
        pix_points, opt_type, self.speed, absolute = self.grouping(self.exec_content)
        self.pix_points = pix_points

        if opt_type in self.arm_exec_content_str:
            self.exec_content = list()
        else:
            # 根据截图中的像素坐标，根据dpi和起始点坐标，换算到物理距离中毫米为单位的坐标
            self.exec_content = self.transform_pix_point(pix_points, absolute)
        # 龙门架机械臂self.exec_content是列表（放点击的坐标），所以会找self.func这个方法来执行（写在基类的流程中）
        # 旋转机械臂self.exec_content是字符串命令，所以会找self.str_func这个方法来执行
        self.func = getattr(self, opt_type)
        return normal_result

    def get_device_obj(self):
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        return device_obj

    @allot_serial_obj
    def click(self, axis, **kwargs):
        """
        # 单击，支持连续单击，例如：拨号
        axis: [[]]  eg: [[100,200]]
        """
        # 对坐标进行预处理
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])
        click_orders = self.__list_click_order(axis)
        ignore_reset = self.kwargs.get("ignore_arm_reset")
        self.ignore_reset = ignore_reset
        kwargs["exec_serial_obj"].send_list_order(click_orders, ignore_reset=ignore_reset)
        click_result = kwargs["exec_serial_obj"].recv(**self.kwargs)
        if CORAL_TYPE == 5.3:
            time.sleep(1)
        if CORAL_TYPE == 5.5:
            time.sleep(2)
        return click_result

    @allot_serial_obj
    def double_click(self, axis, **kwargs):
        """
        # 双击，在同一个点快速点击两次
        axis：list eg:[[10,200]]
        """
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])
        double_click_orders = self.__double_click_order(axis[0])
        kwargs["exec_serial_obj"].send_list_order(double_click_orders)
        return kwargs["exec_serial_obj"].recv(**self.kwargs)

    @allot_serial_obj
    def long_press(self, axis, swipe_time=SWIPE_TIME, **kwargs):
        """
        长按
        axis:[[],[]] eg: [[201, 20], [201, 20]]
        """
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])

        long_click_orders = self.__single_click_order(axis[0])
        kwargs["exec_serial_obj"].send_list_order(long_click_orders[:2],
                                                  other_orders=[long_click_orders[-1]],
                                                  wait=True, wait_time=self.speed)
        self.ignore_reset = True
        return kwargs["exec_serial_obj"].recv(**self.kwargs)

    @allot_serial_obj
    def sliding(self, axis, **kwargs):
        """
        # 滑动
        # 2021.12.17 滑动，self.speed是滑动时间
        point:[[],[]] eg:[[201, 20], [201, 20]]
        """
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])

        swipe_speed = self.cal_swipe_speed(axis)

        sliding_order = self.__sliding_order(axis[0], axis[1], swipe_speed, arm_num=kwargs["arm_num"])

        if CORAL_TYPE in [5, 5.1, 5.2]:
            return kwargs["exec_serial_obj"].send_and_read(sliding_order)

        if CORAL_TYPE == 5.3 or CORAL_TYPE == 5.5:
            # 双指机械臂在滑动前，先判断另一个机械臂是否为idle状态
            other_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(self._model.pk, arm_com_1)) if kwargs[
                                                                                                               "arm_num"] == 0 else hand_serial_obj_dict.get(
                get_hand_serial_key(self._model.pk, arm_com))
            while not other_serial_obj.check_hand_status():
                time.sleep(0.3)
            kwargs["exec_serial_obj"].send_and_read(sliding_order)
            return 0

        kwargs["exec_serial_obj"].send_list_order(sliding_order)

        if swipe_speed == 10000:
            self.ignore_reset = True

        sliding_result = kwargs["exec_serial_obj"].recv(**self.kwargs)
        return sliding_result

    @allot_serial_obj
    def repeat_slide_order(self, axis, *args, **kwargs):
        """
        :param axis: [[起点坐标], [终点坐标]]
        :param args:
        :param kwargs:
        :return:
        """
        # 对坐标进行预处理
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])
        # 计算滑动速度
        swipe_speed = self.cal_swipe_speed(axis)
        # 生成滑动指令集
        self.kwargs["repeat_sliding_order"] = self.__sliding_order(axis[0], axis[1], swipe_speed,
                                                                   arm_num=kwargs["arm_num"])

        self.kwargs["exec_repeat_sliding_obj"] = kwargs["exec_serial_obj"]

        return 0

    @allot_serial_obj
    def fast_swipe_orders(self, axis, *args, **kwargs):
        # 对坐标进行预处理
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])

        # 计算滑动速度
        swipe_speed = self.speed * 60
        # 生成滑动指令集
        self.kwargs["repeat_sliding_order"] = self.fast_sliding_order(axis[0], axis[1], swipe_speed)

        self.kwargs["exec_repeat_sliding_obj"] = kwargs["exec_serial_obj"]
        self.kwargs["sliding_spend_time"] = ((np.hypot(axis[1][0] - axis[0][0],
                                                       axis[1][1] - axis[0][1])) / swipe_speed) * 60
        return 0

    def repeat_sliding(self, *args, **kwargs):
        # 传入滑动重复次数
        if isinstance(self.speed, int) and 1 <= self.speed <= 10:
            repeat_time = self.speed  # 为整型，且需在1-10之间
        else:
            raise RepeatTimeInvalid
        for repeat_num in range(repeat_time):
            ignore_reset = False if repeat_num == (repeat_time - 1) else True
            self.kwargs["exec_repeat_sliding_obj"].send_list_order(self.kwargs["repeat_sliding_order"],
                                                                   ignore_reset=ignore_reset)
            time.sleep(0.5)
        self.kwargs["exec_repeat_sliding_obj"].recv(buffer_size=repeat_time * 8 * 4)
        return 0

    def repeat_fast_sliding(self, *args, **kwargs):
        if CORAL_TYPE == 5.3 or CORAL_TYPE == 5.5:
            raise TcabNotAllowExecThisUnit
        # 传入滑动重复次数
        if isinstance(self.speed, int) and 1 <= self.speed <= 50:
            repeat_time = self.speed  # 为整型，且需在1-50之间
        else:
            raise RepeatTimeInvalid

        for repeat_num in range(repeat_time):
            ignore_reset = False if repeat_num == (repeat_time - 1) else True
            self.kwargs["exec_repeat_sliding_obj"].send_list_order(self.kwargs["repeat_sliding_order"],
                                                                   ignore_reset=ignore_reset)
            if repeat_num > 1 and repeat_num % 2 == 0:
                time.sleep(self.kwargs["sliding_spend_time"] * 7)

        time.sleep(2)
        self.kwargs["exec_repeat_sliding_obj"].recv(buffer_size=40 * repeat_time, is_init=True)
        return 0

    def record_repeat_count(self, *args, **kwargs):
        if isinstance(self.speed, int) and 1 <= self.speed <= 10:
            self.repeat_count = self.speed  # 为整型，且需在1-10之间
        else:
            raise RepeatTimeInvalid
        return 0

    @allot_serial_obj
    def repeat_click(self, axis, *args, **kwargs):
        # 连续多次点击, 先记录所有要点击的点，记录完成后，进行重复点击
        # 暂不支持5D执行该unit
        if CORAL_TYPE == 5.3 or CORAL_TYPE == 5.5:
            raise TcabNotAllowExecThisUnit
        axis = pre_point(axis[0], arm_num=kwargs["arm_num"])
        exec_serial_obj = kwargs["exec_serial_obj"]
        self.repeat_click_dict.update({kwargs.get("index"): {"exec_obj": exec_serial_obj, "axis": axis}})
        if kwargs.get("index") == kwargs.get("length") - 1:
            # 说明是最后一个坐标了
            self.exec_repeat_click()
            return 0

    def exec_repeat_click(self):
        exec_obj = None
        for count in range(self.repeat_count):
            for exec_info in self.repeat_click_dict.values():
                order = self.__single_click_order(exec_info["axis"])
                exec_info["exec_obj"].send_list_order(order, ignore_reset=True)
                exec_obj = exec_info["exec_obj"]
            exec_obj.recv(128)
        return 0

    @allot_serial_obj
    def trapezoid_slide(self, axis, **kwargs):
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])
        # 用力滑动，会先计算滑动起始/终止点的  同方向延长线坐标，并做梯形滑动
        # speed = self.cal_swipe_speed(axis)
        sliding_order = self.__sliding_order(axis[0], axis[1], self.speed, normal=False, arm_num=kwargs["arm_num"])
        kwargs["exec_serial_obj"].send_list_order(sliding_order)
        return kwargs["exec_serial_obj"].recv(**self.kwargs)

    @allot_serial_obj
    def straight_swipe(self, axis, **kwargs):
        # 采用直角梯形滑动，目前仅支持上滑
        if axis[1][1] >= axis[0][1]:
            raise InvalidCoordinates
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])
        sliding_order = self.__straight_sliding_order(axis[0], axis[1], self.speed, arm_num=kwargs["arm_num"])
        kwargs["exec_serial_obj"].send_list_order(sliding_order)
        if kwargs['arm_num'] == 1: time.sleep(0.5)
        return kwargs["exec_serial_obj"].recv(**self.kwargs)

    def reset_hand(self, rotate=False, **kwargs):
        # 恢复手臂位置 可能是龙门架也可能是旋转机械臂
        serial_obj = None
        if rotate is True:
            serial_obj = rotate_hand_serial_obj_dict.get(self._model.pk)
            self._model.logger.info(f"reset hand order:{arm_move_position}")
            serial_obj.send_single_order(arm_move_position)
        else:
            for obj_key in hand_serial_obj_dict.keys():
                if obj_key.startswith(self._model.pk):
                    serial_obj = hand_serial_obj_dict.get(obj_key)
                    reset_order = get_wait_position(serial_obj.ser.port)
                    self._model.logger.info(f"reset hand order:{reset_order}")
                    serial_obj.send_single_order(reset_order)
        serial_obj.recv()
        return 0

    def continuous_swipe(self, commend, **kwargs):
        # 连续滑动方法，多次滑动之间不抬起，执行完不做等待
        arm_num = 0
        exec_serial_obj = None
        if CORAL_TYPE != 5.3 and CORAL_TYPE != 5.5:
            exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(self._model.pk, arm_com))
        else:
            # if kwargs.get('index', 0) == 0:
            exec_serial_obj, arm_num = judge_start_x(commend[0][0], self._model.pk)

        commend[0] = pre_point(commend[0], arm_num=arm_num)
        commend[1] = pre_point(commend[1], arm_num=arm_num)
        sliding_order = self._sliding_contious_order(commend[0], commend[1], kwargs.get('index', 0),
                                                     kwargs.get('length', 0), arm_num=arm_num)
        exec_serial_obj.send_list_order(sliding_order, ignore_reset=True)
        return exec_serial_obj.recv()

    @allot_serial_obj
    def continuous_swipe_2(self, points, **kwargs):
        exec_serial_obj = kwargs.get('exec_serial_obj')
        # 对坐标进行预处理
        for axis_index in range(len(points)):
            points[axis_index] = pre_point(points[axis_index], arm_num=kwargs["arm_num"])

        # 先加一条移动过去的指令
        sliding_order = [
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (points[0][0], points[0][1], Z_UP, MOVE_SPEED)
        ]
        for point_index in range(len(points)):
            point = points[point_index]
            speed = MOVE_SPEED if point_index == 0 else self.speed
            sliding_order += ['G01 X%0.1fY%0.1fZ%dF%d \r\n' % (point[0], point[1], point[2], speed)]
        # 最后再加一条，抬起来的指令
        sliding_order += ['G01 X%0.1fY%0.1fZ%dF%d \r\n' % (points[-1][0], points[-1][1], Z_UP, MOVE_SPEED)]

        # 1条31的发送过去
        exec_serial_obj.recv(buffer_size=128, is_init=True)
        for order_index in range(0, len(sliding_order), 1):
            ignore_reset = False if (order_index + 1) >= len(sliding_order) else True
            begin_time = time.time()
            exec_serial_obj.send_list_order(sliding_order[order_index:order_index + 1], ignore_reset=ignore_reset)
            exec_serial_obj.recv(buffer_size=8, is_init=True)

            # 根据距离，自己计算等待时间
            regex = re.compile("[-\d.]+")
            wait_position = get_wait_position(exec_serial_obj.ser.port)
            if order_index == 0:
                begin_point = [float(point) for point in re.findall(regex, wait_position)[1:4]]
            else:
                begin_point = [float(point) for point in re.findall(regex, sliding_order[order_index - 1])[1:4]]
            end_point = [float(point) for point in re.findall(regex, sliding_order[order_index])[1:4]]
            distance = round(np.linalg.norm(np.array(end_point) - np.array(begin_point)), 2)
            speed = int(re.findall(regex, sliding_order[order_index])[-1])
            print(distance, speed)

            # 换算成以秒为单位的时间
            spend_time = (distance / speed) * 60
            while time.time() - begin_time < spend_time:
                time.sleep(0.1)

    def back(self, _, **kwargs):
        # 按返回键，需要在5#型柜 先配置过返回键的位置
        device_obj = self.get_device_obj()
        point = self.calculate([device_obj.back_x, device_obj.back_y, device_obj.back_z], absolute=False)
        exec_serial_obj, arm_num = judge_start_x(point[0], self._model.pk)
        point = pre_point(point, arm_num=arm_num)
        if kwargs.get("is_double", False):
            click_orders = self.__double_click_order(point)
        else:
            click_orders = self.__single_click_order(point)
        exec_serial_obj.send_list_order(click_orders)
        click_back_result = exec_serial_obj.recv()
        return click_back_result

    def double_back(self, _, **kwargs):
        # 双击返回键  同5#型柜使用
        return self.back(is_double=True)

    def home(self, _, **kwargs):
        # 点击桌面键 5#型柜使用
        device_obj = self.get_device_obj()
        point = self.calculate([device_obj.home_x, device_obj.home_y, device_obj.home_z], absolute=False)
        exec_serial_obj, arm_num = judge_start_x(point[0], self._model.pk)
        point = pre_point(point, arm_num=arm_num)
        click_orders = self.__single_click_order(point)
        exec_serial_obj.send_list_order(click_orders)
        click_home_result = exec_serial_obj.recv()
        return click_home_result

    def menu(self, _, **kwargs):
        # 点击菜单键 5#型柜使用
        device_obj = self.get_device_obj()
        point = self.calculate([device_obj.menu_x, device_obj.menu_y, device_obj.menu_z], absolute=False)
        exec_serial_obj, arm_num = judge_start_x(point[0], self._model.pk)
        point = pre_point(point, arm_num=arm_num)
        click_orders = self.__single_click_order(point)
        if kwargs.get("is_long_press", False):
            exec_serial_obj.send_list_order(click_orders[:2], other_orders=[click_orders[-1]], wait=True)
        else:
            exec_serial_obj.send_list_order(click_orders)
        click_menu_result = exec_serial_obj.recv()
        return click_menu_result

    def long_press_menu(self, _, **kwargs):
        # 长按菜单键 5#型柜使用
        return self.menu(is_long_press=True)

    def press_custom_point(self, pix_point, **kwargs):
        """
        点击 or 按压实体键
        Tcab-5D 不支持侧边键按压
        """
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        roi = [device_obj.x1, device_obj.y1, device_obj.x2, device_obj.y2]
        from app.v1.Cuttle.macPane.pane_view import PaneClickTestView
        try:
            exec_serial_obj, orders, exec_action = PaneClickTestView.get_exec_info(pix_point[0], pix_point[1],
                                                                                   pix_point[2],
                                                                                   self._model.pk,
                                                                                   roi=[float(value) for value in roi],
                                                                                   is_normal_speed=True)
        except TcabNotAllowExecThisUnit:
            raise TcabNotAllowExecThisUnit
        except CoordinatesNotReasonable:
            raise CoordinatesNotReasonable
        ret = PaneClickTestView.exec_hand_action(exec_serial_obj, orders, exec_action, wait_time=self.speed)
        # 点击完自定义按键复位机械臂
        redis_client.set(f'{ARM_COUNTER_PREFIX}{exec_serial_obj.com_id}', ARM_RESET_THRESHOLD + 1)
        return ret

    def arm_back_home(self, *args, **kwargs):
        arm_com = self.kwargs.get('arm_com', '')
        for obj_key in hand_serial_obj_dict.keys():
            # 对指定的机械臂进行复位操作
            if obj_key.startswith(self._model.pk) and arm_com in obj_key:
                serial_obj = hand_serial_obj_dict.get(obj_key)
                # 这里应该根据端口号，获取back_order，因为不同的机械臂等待位置不一样
                back_order = self.arm_back_home_order(serial_obj)
                for order in back_order:
                    serial_obj.send_single_order(order)
                    serial_obj.recv(buffer_size=32, is_init=True)
                # 只要复位就重新计数
                redis_client.set(f'{ARM_COUNTER_PREFIX}{arm_com}', 0)
        return 0

    @allot_serial_obj
    def taier_click_center_point(self, pix_point, **kwargs):
        """
        泰尔实验室，打点精度测试
        """
        cur_index = kwargs.get('index')
        dis_filename = os.path.join(self.kwargs.get("rds_work_path"), '打点精度.txt')

        try:
            from app.v1.Cuttle.macPane.pane_view import ClickCenterPointFive
            # 保存到rds目录中，这样方便调试
            pre_filename = os.path.join(self.kwargs.get("rds_work_path"), f'point_{cur_index - 1}.png')
            filename = os.path.join(self.kwargs.get("rds_work_path"), f'point_{cur_index}.png')
            device_obj = self.get_device_obj()

            if cur_index == 0:
                ret_code = device_obj.get_snapshot(pre_filename, max_retry_time=1, original=False)
            else:
                ret_code = 0

            if ret_code == 0:
                click_center_point_five = ClickCenterPointFive()
                pre_red_points = click_center_point_five.get_red_point(pre_filename)

                self.click(pix_point)

                # 拍照之前等待一下，否则机械臂会盖住摄像头
                time.sleep(1)
                # 每次只处理一个红点
                ret_code = device_obj.get_snapshot(filename, max_retry_time=1, original=False)
                if ret_code == 0:
                    red_points = click_center_point_five.get_red_point(filename)
                    print(f'{cur_index + 1}之前的红点', pre_red_points)
                    print(f'{cur_index + 1}当前的红点', red_points)
                    # 将上次的红点减掉，以免对算法产生干扰
                    red_points = click_center_point_five.sub_point(pre_red_points, red_points)
                    print(f'{cur_index + 1}剩下的红点', red_points)
                    print('要点击的点', self.pix_points)

                    # 计算俩点之间的距离
                    self.get_point_dis(red_points, self.pix_points, dis_filename, cur_index)
        except Exception:
            print(traceback.format_exc())
            return 1

        return 0

    @allot_serial_obj
    def taier_draw_line(self, pix_point, **kwargs):
        """
        泰尔实验室，画线精度测试
        """
        cur_index = kwargs.get('index')
        dis_filename = os.path.join(self.kwargs.get("rds_work_path"), '画线精度.txt')

        try:
            from app.v1.Cuttle.macPane.pane_view import ClickCenterPointFive
            # 保存到rds目录中，这样方便调试
            pre_filename = os.path.join(self.kwargs.get("rds_work_path"), f'line_{cur_index - 1}.png')
            filename = os.path.join(self.kwargs.get("rds_work_path"), f'line_{cur_index}.png')
            device_obj = self.get_device_obj()

            if cur_index == 0:
                ret_code = device_obj.get_snapshot(pre_filename, max_retry_time=1, original=False)
            else:
                ret_code = 0

            if ret_code == 0:
                click_center_point_five = ClickCenterPointFive()
                pre_lines = click_center_point_five.get_lines(pre_filename)

                self.sliding(pix_point)

                # 拍照之前等待一下，否则机械臂会盖住摄像头
                sleep_time = self.speed / 1000
                # 机械臂移动速度算的有问题应该，实际测试的时候，22秒的时候实际机械臂并没有移动完
                if sleep_time > 20:
                    sleep_time += 4
                elif sleep_time > 10:
                    sleep_time += 3
                else:
                    sleep_time += 1
                print('开始等待', str(sleep_time))
                time.sleep(sleep_time)
                # 每次只处理一个红点
                ret_code = device_obj.get_snapshot(filename, max_retry_time=1, original=False)
                if ret_code == 0:
                    lines = click_center_point_five.get_lines(filename)
                    print(f'{cur_index + 1}之前的线', pre_lines)
                    print(f'{cur_index + 1}当前的线', lines)
                    # 将上次的红点减掉，以免对算法产生干扰
                    lines = click_center_point_five.sub_point(pre_lines, lines)
                    print(f'{cur_index + 1}剩下的线', lines)
                    print('画线的起点', self.pix_points)

                    # 永远取左边的点，如果完全垂直，则取上边的点
                    if self.pix_points[0] < self.pix_points[2] and abs(self.pix_points[0] - self.pix_points[2]) > 7:
                        left_points = self.pix_points[:2]
                    elif self.pix_points[0] > self.pix_points[2] and abs(self.pix_points[0] - self.pix_points[2]) > 7:
                        left_points = self.pix_points[2:]
                    else:
                        if self.pix_points[1] < self.pix_points[3]:
                            left_points = self.pix_points[:2]
                        else:
                            left_points = self.pix_points[2:]

                    self.get_point_dis(lines, left_points, dis_filename, cur_index)
        except Exception:
            print(traceback.format_exc())
            return 1

        return 0

    def taier_breakpoint(self, pix_point, **kwargs):
        """
        泰尔实验室，回型框断点检测
        """
        from app.v1.Cuttle.macPane.pane_view import ClickCenterPointFive
        # 保存到rds目录中，这样方便调试
        filename = os.path.join('break_point.png')
        result_filename = os.path.join(self.kwargs.get("rds_work_path"), f'result.png')

        self.continuous_swipe_2(pix_point)

        # 根据坐标点先做一个等待，等后期优化
        time.sleep(1)
        device_obj = self.get_device_obj()
        device_obj.get_snapshot(filename, max_retry_time=1, original=False)
        click_center_point_five = ClickCenterPointFive()
        success = click_center_point_five.get_contours(filename, result_filename)

        return success if success == 0 else 1

    def get_point_dis(self, points, pix_points, dis_filename, cur_index):
        # 计算俩点之间的距离
        dis = math.sqrt(math.pow(points[0][0] - pix_points[0], 2) +
                        math.pow(points[0][1] - pix_points[1], 2))
        dis = round(dis, 2)

        print('像素差别', dis)
        dpi = get_global_value('pane_dpi')
        if dpi is None:
            raise CoordinateConvert()

        dis = round(dis / dpi, 2)
        print('毫米差别', dis)
        with open(dis_filename, 'a') as dis_file:
            dis_file.write(f'{cur_index + 1}. ' + str(dis))
            dis_file.write('\n')

    def _find_key_point(self, name):
        from app.v1.device_common.device_model import Device
        response = request(url=phone_model_url, params={"phone_model_name": Device(pk=self._model.pk).phone_model_name,
                                                        "fields": name}
                           , filter_unique_key=True)
        position = response.get(name)
        if not position:
            raise KeyPositionUsedBeforesSet
        return position

    def str_func(self, commend, **kwargs):
        from app.v1.device_common.device_model import Device
        move = False
        sleep_time = 0
        rotate = True
        # 三轴机械臂移动 为了和旋转机械臂区分 加了前缀
        if commend.startswith(f'{hand_origin_cmd_prefix} G01'):
            if Device(pk=self._model.pk).has_arm is False:
                return -10
            target_hand_serial_obj_dict = hand_serial_obj_dict
            rotate = False
            commend = commend.replace(hand_origin_cmd_prefix, '')
        else:
            if Device(pk=self._model.pk).has_rotate_arm is False:
                return -9
            target_hand_serial_obj_dict = rotate_hand_serial_obj_dict
        # 默认是旋转机械臂执行的方法
        if '<rotateSleep>' in commend:
            # 长按的等待操作，等待输入的时间+wait_bias时间。
            res = re.search("<rotateSleep>(.*?)$", commend)
            sleep_time = res.group(1)
            commend = commend.replace("<rotateSleep>" + sleep_time, "")
        if '<move>' in commend:
            # 归位操作，用于长按电源后归reset位置。
            commend = commend.replace('<move>', "")
            move = True
        target_hand_serial_obj_dict.get(self._model.pk).send_single_order(commend)
        if move:
            self.reset_hand(rotate=rotate, **kwargs)
        target_hand_serial_obj_dict.get(self._model.pk).recv()
        self.ignore_reset = True
        return 0

    def rotate(self, commend):
        return self.str_func(commend)

    def open_usb_power(self, *args, **kwargs):
        self.ignore_reset = True
        controlUsbPower(status="ON")

    def close_usb_power(self, *args, **kwargs):
        self.ignore_reset = True
        controlUsbPower(status="OFF")

    def after_unit(self, **kwargs):
        # unit执行完 5型柜执行移开的操作，防止长时间遮挡摄像头
        if self.ignore_reset is False and math.floor(CORAL_TYPE) == 5:
            self.reset_hand(**kwargs)

    def double_hand_swipe(self, *args, **kwargs):
        """
        # 计算滑动速度
        # 生成指令
        # 执行指令
        :return:
        """
        left_swipe_speed = self.cal_swipe_speed(self.double_hand_point[0])
        right_swipe_speed = self.cal_swipe_speed(self.double_hand_point[1])
        left_order = self.__sliding_order(self.double_hand_point[0][0], self.double_hand_point[0][1],
                                          speed=left_swipe_speed)
        right_order = self.__sliding_order(self.double_hand_point[1][0], self.double_hand_point[1][1],
                                           speed=right_swipe_speed)
        self.exec_double_hand_swipe(left_order, right_order)
        if min(left_swipe_speed, right_swipe_speed) < 2000:
            time.sleep(self.speed + 0.5)
        hand_serial_obj_dict.get(get_hand_serial_key(self._model.pk, arm_com)).recv(64)
        hand_serial_obj_dict.get(get_hand_serial_key(self._model.pk, arm_com_1)).recv(64)
        return 0

    def record_double_hand_point(self, axis, *args, **kwargs):
        """
        判断坐标的合理性，对双指滑动的坐标进行转换，并记录
        :param axis: [[左机械臂点],[左机械臂点],[右机械臂点],[右机械臂点]]
        """
        self.judge_axis_reasonable(axis)
        left_point = [pre_point(axis[0]), pre_point(axis[1])]
        right_point = [pre_point(axis[2], arm_num=1), pre_point(axis[3], arm_num=1)]
        self.double_hand_point = [left_point, right_point]
        return 0

    def cal_swipe_speed(self, axis, *args, **kwargs):
        """
        :param axis: [[起点坐标], [终点坐标]]
        :return:
        """
        swipe_distance = np.hypot(axis[1][0] - axis[0][0], axis[1][1] - axis[0][1])
        cal_swipe_speed = swipe_distance / (self.speed * 0.00002)
        swipe_speed = cal_swipe_speed if cal_swipe_speed < 10000 else 10000
        return swipe_speed

    def exec_double_hand_swipe(self, left_order, right_order):
        left_obj = hand_serial_obj_dict.get(get_hand_serial_key(self._model.pk, arm_com))
        right_obj = hand_serial_obj_dict.get(get_hand_serial_key(self._model.pk, arm_com_1))

        exec_t1 = threading.Thread(target=left_obj.send_list_order, args=[[left_order[0]]],
                                   kwargs={"ignore_reset": True})
        exec_t2 = threading.Thread(target=right_obj.send_list_order, args=[[right_order[0]]],
                                   kwargs={"ignore_reset": True})

        exec_t1.start()
        exec_t2.start()

        while exec_t1.is_alive() or exec_t2.is_alive():
            continue

        while (not left_obj.check_hand_status()) or (not right_obj.check_hand_status()):
            time.sleep(1)

        exec2_t1 = threading.Thread(target=left_obj.send_and_read, args=[left_order[1:]], )
        exec2_t2 = threading.Thread(target=right_obj.send_and_read, args=[right_order[1:]])

        exec2_t2.start()
        exec2_t1.start()

        while exec2_t2.is_alive() or exec2_t1.is_alive():
            continue

        return 0

    def judge_axis_reasonable(self, axis):
        """
        判断双指滑动坐标的合理性,
        2022.4.22 目前仅支持双指缩小和放大的坐标合理性判断
        axis：[[左机械臂起点],[左机械臂终点],[右机械臂起点],[右机械臂终点]]
        判断逻辑: 左机械臂起点终点的X值均需小于右机械臂的起点和终点的X值
                四个点之间的X轴间距必须保持安全距离
        :return:
        """
        if axis[0][0] >= axis[2][0] or axis[1][0] > axis[3][0]:
            raise InvalidCoordinates
        self.judge_diff_x(axis[0][0], axis[2][0])
        self.judge_diff_x(axis[1][0], axis[2][0])
        self.judge_diff_x(axis[0][0], axis[3][0])
        self.judge_diff_x(axis[1][0], axis[3][0])
        judge_result, cross_point = DefaultMixin.judge_cross([axis[0][0], axis[0][1], axis[1][0], axis[1][1]],
                                                             [axis[2][0], axis[2][1], axis[3][0], axis[3][1]])
        if not judge_result:
            raise InvalidCoordinates
        left_arm_x = [min(axis[0][0], axis[1][0]), max(axis[0][0], axis[1][0])]
        right_arm_x = [min(axis[2][0], axis[3][0]), max(axis[2][0], axis[3][0])]
        if left_arm_x[0] <= cross_point[0] <= left_arm_x[1] or right_arm_x[0] <= cross_point[0] <= right_arm_x[1]:
            raise InvalidCoordinates
        return 0

    @staticmethod
    def judge_diff_x(left_x, right_x):
        # 防撞机制
        # 距离最近的两个点，x坐标差值不得小于安全值
        if abs(left_x - right_x) > DIFF_X:
            return True
        raise InvalidCoordinates

    def __list_click_order(self, axis_list):
        click_orders = []
        for axis in axis_list:
            click_order = self.__single_click_order(axis)
            click_orders.extend(click_order)
        return click_orders

    def __single_click_order(self, axis):
        performance_start_speed = MOVE_SPEED
        if self.performance_start_point:
            performance_start_speed = 500
        return [
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2] + 5, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2], MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], Z_UP, MOVE_SPEED),
        ]

    @staticmethod
    def _press_button_order(axis):
        axis_x, axis_y = axis
        if axis_x > HAND_MAX_X or axis_y > HAND_MAX_Y:
            return {"error:Invalid Pix_Point"}
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, get_global_value('Z_DOWN') + 5, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, get_global_value('Z_DOWN'), MOVE_SPEED),
            # 'G01 Z%dF%d \r\n' % (Z_DOWN, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_UP, MOVE_SPEED),
            # 'G01 Z%dF%d \r\n' % (Z_UP, MOVE_SPEED)
        ]

    @staticmethod
    def __double_click_order(axis):
        return [
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2] + 5, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2], MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], Z_UP, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2], MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], Z_UP, MOVE_SPEED),
        ]

    @staticmethod
    def __sliding_order(start_point, end_point, speed=MOVE_SPEED, normal=True, arm_num=0):
        start_x, start_y, start_z = start_point
        end_x, end_y, _ = end_point
        if normal:
            commend_list = [
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, start_y, start_z + 5, MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, start_y, start_z, MOVE_SPEED),
                'G01 X%0.1fY%0.1fF%d \r\n' % (end_x, end_y, speed),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (end_x, end_y, Z_UP, MOVE_SPEED),
            ]
            return commend_list
        else:
            start_x, start_y, end_x, end_y = [abs(num) for num in [start_x, start_y, end_x, end_y]]
            x1 = min(max(start_x - (end_x - start_x) * 10 / np.abs(end_x - start_x) * trapezoid, 0), 120)
            y1 = min(max(start_y - (end_y - start_y) * 10 / np.abs((end_y - start_y)) * trapezoid, 0), 150)
            x4 = min(max(end_x + (end_x - start_x) * trapezoid, 0), 150)
            y4 = min(max(end_y + (end_y - start_y) * trapezoid, 0), 150)
            y1, start_y, end_y, y4 = [-num for num in [y1, start_y, end_y, y4]]
            if arm_num == 1:
                x1, start_x, end_x, x4 = [-num for num in [x1, start_x, end_x, x4]]
            return [
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (x1, y1, Z_START, MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, start_y, start_z - 1, MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (end_x, end_y, start_z + 3, speed),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (x4, y4, Z_UP, MOVE_SPEED),
            ]

    def fast_sliding_order(self, start_point, end_point, speed=MOVE_SPEED):
        start_x, start_y, start_z = start_point
        end_x, end_y, _ = end_point
        commend_list = [
            'G01 X%0.1fY%0.1fZ%0.1fF%d \r\n' % (start_x, start_y, start_z + 2, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%0.1fF%d \r\n' % (start_x, start_y, start_z, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%0.1fF%d \r\n' % (end_x, end_y, start_z, speed),
        ]
        return commend_list

    @staticmethod
    def __straight_sliding_order(start_point, end_point, speed=MOVE_SPEED, arm_num=0):
        """
        目前仅支持上滑
        最后一点的Y值目前限制在 [0, 150]范围内
        X值也限制在[0,150]范围内
        后续优化，可将y值范围限制在[0, end_y]
        x值限制在[0, m_location[0]+手机宽度] 或者 [0, hand_x-max(m_location[0], 30)]
        """
        start_x, start_y, start_z = start_point
        end_x, end_y, _ = end_point
        start_y, end_y = abs(start_y), abs(end_y)
        y4 = min(max(end_y + (end_y - start_y) * trapezoid, 0), 150)
        if arm_num == 0:
            x4 = min(max(end_x + (end_x - start_x) * trapezoid, 0), 150)
        else:
            start_x, end_x = abs(start_x), abs(end_x)
            x4 = -min(max(end_x + (end_x - start_x) * trapezoid, 0), 150)
            start_x, end_x = -start_x, -end_x
        return [
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, -start_y, Z_START, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, -start_y, start_z, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (end_x, -end_y, start_z + 3, speed),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (x4, -y4, Z_UP, MOVE_SPEED),
        ]

    @staticmethod
    def _sliding_contious_order(start_point, end_point, commend_index, commend_length, arm_num=0):
        start_x, start_y, start_z = start_point
        end_x, end_y, _ = end_point
        # 连续滑动保证动作无偏差
        from app.v1.Cuttle.basic.setting import last_swipe_end_point
        # 在4,5 型号柜1代表毫米，其他型柜15代表像素，所以这里做区分。
        th = 15 if CORAL_TYPE < 4 else 1
        # 如果前一滑动的终止点和下一次滑动的起始点很接近，我们认为就是要连续滑动，直接把其赋值为相同点。并且每次都缓存此次的终止点做下次对比
        if np.abs(abs(start_x) - abs(last_swipe_end_point[0])) < th and np.abs(
                abs(start_y) - abs(last_swipe_end_point[1])) < th:
            start_x, start_y = last_swipe_end_point
        last_swipe_end_point[0] = end_x
        last_swipe_end_point[1] = end_y
        # 首次动作有移动和下压动作
        if commend_index == 0:
            return [
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_START, MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (start_x, start_y, start_z, MOVE_SPEED),
                'G01 X%0.1fY%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED)
            ]
        elif commend_index + 1 != commend_length:  # 后面动作只有滑动
            return [
                'G01 X%0.1fY%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED)
            ]
        else:
            return [
                'G01 X%0.1fY%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (end_x, end_y, Z_START, MOVE_SPEED)
            ]

    @staticmethod
    def press_side_order(pix_point, is_left=False, **kwargs):
        """
        :param point: 要按压的侧边键坐标 eg：[x,y,z]
        :param is_left: 是否是左侧边键
        :return: 返回按压指令集
        """
        x_offset = pix_point[0] - X_SIDE_KEY_OFFSET if is_left else pix_point[0] + X_SIDE_KEY_OFFSET
        speed = kwargs['speed'] if kwargs.get('speed') else MOVE_SPEED
        press_side_speed = kwargs['press_side_speed'] if kwargs.get('press_side_speed') else PRESS_SIDE_KEY_SPEED
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x_offset, pix_point[1], Z_START, speed),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x_offset, pix_point[1], pix_point[2], speed),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (pix_point[0], pix_point[1], pix_point[2], press_side_speed),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x_offset, pix_point[1], pix_point[2], press_side_speed),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x_offset, pix_point[1], Z_START, speed),
        ]

    @staticmethod
    def arm_back_home_order(serial_obj):
        wait_position = get_wait_position(serial_obj.ser.port)
        return [
            'G01 Z%dF5000 \r\n' % Z_UP,
            '$H \r\n',
            'G92 X0Y0Z0 \r\n',
            'G90 \r\n',
            wait_position,
        ]


if __name__ == '__main__':

    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id="COM9")
    hand_reset_orders = ['G01 X20Y-95.0Z0F15000 \r\n']
    init = [
        "$x \r\n",
        "$h \r\n",
        "G92 X0Y0Z0 \r\n",
        "G90 \r\n"
    ]
    for g_orders in init:
        hand_serial_obj.send_single_order(g_orders)
        result = hand_serial_obj.recv(buffer_size=64)

    # hand_serial_obj.timeout =1
    # hand_serial_obj.connect(com_id="COM9")
    for i in range(10):
        for g_orders in hand_reset_orders:
            a = time.time()
            hand_serial_obj.send_single_order(g_orders)
            response = hand_serial_obj.recv(buffer_size=2)
            print(time.time() - a)

        # SerialTimeoutException
