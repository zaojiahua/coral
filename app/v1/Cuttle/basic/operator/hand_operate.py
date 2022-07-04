import math
import re
import threading
import time

import numpy as np

from app.config.setting import CORAL_TYPE, arm_com, arm_com_1
from app.config.url import phone_model_url
from app.execption.outer.error_code.hands import KeyPositionUsedBeforesSet, ChooseSerialObjFail, InvalidCoordinates, \
    InsufficientSafeDistance, RepeatTimeInvalid, TcabNotAllowExecThisUnit
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.default_calculate import DefaultMixin
from app.v1.Cuttle.basic.hand_serial import HandSerial, controlUsbPower, SensorSerial
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.setting import HAND_MAX_Y, HAND_MAX_X, SWIPE_TIME, Z_START, Z_UP, MOVE_SPEED, \
    hand_serial_obj_dict, normal_result, trapezoid, arm_default, arm_wait_position, \
    arm_move_position, rotate_hand_serial_obj_dict, hand_origin_cmd_prefix, X_SIDE_KEY_OFFSET, \
    sensor_serial_obj_dict, PRESS_SIDE_KEY_SPEED, get_global_value, X_SIDE_OFFSET_DISTANCE, ARM_MOVE_REGION, DIFF_X


def hand_init(arm_com_id, device_obj, **kwargs):
    # 龙门架机械臂初始化
    """
    1. 解锁机械臂，并将机械臂移动至Home位置
    2. 设置坐标模式为绝对值模式
    3. 设置HOME点为操作原点
    :return:
    """
    if CORAL_TYPE == 5.3:
        obj_key = device_obj.pk + arm_com_id
    else:
        obj_key = device_obj.pk

    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id=arm_com_id)
    hand_serial_obj_dict[obj_key] = hand_serial_obj
    hand_reset_orders = [
        "$x \r\n",
        "$h \r\n",
        f"G92 X0Y0Z0 \r\n",
        "G90 \r\n",
        arm_wait_position
    ]
    for orders in hand_reset_orders:
        hand_serial_obj.send_single_order(orders)
        hand_serial_obj.recv(buffer_size=64, is_init=True)
    return 0


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
        x_point = HAND_MAX_X - point[0]
        return [-x_point, -point[1], z_point]
    raise ChooseSerialObjFail


def judge_start_x(start_x_point, device_level):
    arm_num = 0
    if CORAL_TYPE == 5.3:
        suffix_key = arm_com if start_x_point < ARM_MOVE_REGION[0] else arm_com_1
        arm_num = 0 if suffix_key == arm_com else 1
        exec_serial_obj = hand_serial_obj_dict.get(device_level + suffix_key)
    else:
        exec_serial_obj = hand_serial_obj_dict.get(device_level)
    return exec_serial_obj, arm_num


def allot_serial_obj(func):
    # 该函数用来分配执行的机械臂对象
    def wrapper(self, axis, **kwargs):
        start_x_point = axis[0][0] if type(axis[0]) is list else axis[0]
        exec_serial_obj, arm_num = judge_start_x(start_x_point, self._model.pk)
        kwargs["exec_serial_obj"] = exec_serial_obj
        kwargs["arm_num"] = arm_num
        func(self, axis, **kwargs)

    return wrapper


class HandHandler(Handler, DefaultMixin):
    before_match_rules = {
        # 用在执行之前，before_execute中针对不同方法正则替换其中的相对坐标到绝对坐标
        "input tap": "_relative_point",
        "input swipe": "_relative_swipe",
        "double_point": "_relative_double_point",
        "double hand zoom": "_relative_double_hand",
    }
    arm_exec_content_str = ["arm_back_home", "open_usb_power", "close_usb_power", "cal_swipe_speed",
                            "double_hand_swipe", "repeat_sliding", "record_repeat_count"]

    def __init__(self, *args, **kwargs):
        super(HandHandler, self).__init__(*args, **kwargs)
        self.double_hand_point = None
        self.ignore_reset = False
        self.performance_start_point = kwargs.get('performance_start_point')
        self.kwargs = kwargs
        self.repeat_count = 0
        self.repeat_click_dict = {}

    def before_execute(self):
        # 先转换相对坐标到绝对坐标
        for key, value in self.before_match_rules.items():
            if key in self.exec_content:
                getattr(self, value)()
        # 根据adb指令中的关键词dispatch到对应机械臂方法,pix_points为adb模式下的截图中的像素坐标
        pix_points, opt_type, self.speed, absolute = self.grouping(self.exec_content)

        if opt_type in self.arm_exec_content_str:
            self.exec_content = list()
        else:
            # 根据截图中的像素坐标，根据dpi和起始点坐标，换算到物理距离中毫米为单位的坐标
            self.exec_content = self.transform_pix_point(pix_points, absolute)
        # 龙门架机械臂self.exec_content是列表（放点击的坐标），所以会找self.func这个方法来执行（写在基类的流程中）
        # 旋转机械臂self.exec_content是字符串命令，所以会找self.str_func这个方法来执行
        self.func = getattr(self, opt_type)
        return normal_result

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
    def sliding(self, axis, swipe_time=SWIPE_TIME, **kwargs):
        """
        # 滑动
        # 2021.12.17 滑动，self.speed是滑动时间
        point:[[],[]] eg:[[201, 20], [201, 20]]
        """
        for axis_index in range(len(axis)):
            axis[axis_index] = pre_point(axis[axis_index], arm_num=kwargs["arm_num"])

        swipe_speed = self.cal_swipe_speed(axis)

        sliding_order = self.__sliding_order(axis[0], axis[1], swipe_speed, arm_num=kwargs["arm_num"])

        if CORAL_TYPE == 5.3 or CORAL_TYPE == 5.1:
            return kwargs["exec_serial_obj"].send_and_read(sliding_order)
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

    def repeat_sliding(self, *args, **kwargs):
        # 传入滑动重复次数
        if isinstance(self.speed, int) and 1 <= self.speed <= 10:
            repeat_time = self.speed  # 为整型，且需在1-10之间
        else:
            raise RepeatTimeInvalid
        for i in range(repeat_time):
            ignore_reset = False if i == (repeat_time - 1) else True
            self.kwargs["exec_repeat_sliding_obj"].send_list_order(self.kwargs["repeat_sliding_order"],
                                                                   ignore_reset=ignore_reset)

        self.kwargs["exec_repeat_sliding_obj"].recv(buffer_size=repeat_time * 8)
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
        if CORAL_TYPE == 5.3:
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
        return kwargs["exec_serial_obj"].recv(**self.kwargs)

    def reset_hand(self, reset_orders=arm_wait_position, rotate=False, **kwargs):
        # 恢复手臂位置 可能是龙门架也可能是旋转机械臂
        self._model.logger.info(f"reset hand order:{reset_orders}")
        serial_obj = None
        if rotate is True:
            serial_obj = rotate_hand_serial_obj_dict(self._model.pk)
            serial_obj.send_single_order(reset_orders)
        else:
            for obj_key in hand_serial_obj_dict.keys():
                if obj_key.startswith(self._model.pk):
                    serial_obj = hand_serial_obj_dict.get(obj_key)
                    serial_obj.send_single_order(reset_orders)
        serial_obj.recv()
        return 0

    def continuous_swipe(self, commend, **kwargs):
        # 连续滑动方法，多次滑动之间不抬起，执行完不做等待
        arm_num = 0
        exec_serial_obj = None
        if CORAL_TYPE != 5.3:
            exec_serial_obj = hand_serial_obj_dict.get(self._model.pk)
        else:
            if kwargs.get('index', 0) == 0:
                exec_serial_obj, arm_num = judge_start_x(commend[0][0], self._model.pk)

        commend[0] = pre_point(commend[0], arm_num=arm_num)
        commend[1] = pre_point(commend[1], arm_num=arm_num)
        sliding_order = self._sliding_contious_order(commend[0], commend[1], kwargs.get('index', 0),
                                                     kwargs.get('length', 0), arm_num=arm_num)
        exec_serial_obj.send_list_order(sliding_order, ignore_reset=True)
        return exec_serial_obj.recv()

    def back(self, _, **kwargs):
        # 按返回键，需要在5#型柜 先配置过返回键的位置
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
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
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        point = self.calculate([device_obj.home_x, device_obj.home_y, device_obj.home_z], absolute=False)
        exec_serial_obj, arm_num = judge_start_x(point[0], self._model.pk)
        point = pre_point(point, arm_num=arm_num)
        click_orders = self.__single_click_order(point)
        exec_serial_obj.send_list_order(click_orders)
        click_home_result = exec_serial_obj.recv()
        return click_home_result

    def menu(self, _, **kwargs):
        # 点击菜单键 5#型柜使用
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
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

    def press_side(self, pix_point, **kwargs):
        # 按压侧边键
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        location = get_global_value('m_location')
        DefaultMixin.judge_coordinates_reasonable(pix_point, location[0] + float(device_obj.width), location[0],
                                                  location[2])
        is_left = False if (pix_point[0] - location[1]) > X_SIDE_OFFSET_DISTANCE else True
        press_side_order = self.press_side_order(pix_point, is_left=is_left)
        hand_serial_obj_dict.get(self._model.pk).send_out_key_order(press_side_order[:3],
                                                                    others_orders=press_side_order[3:],
                                                                    wait_time=self.speed)
        rev = hand_serial_obj_dict.get(self._model.pk).recv(buffer_size=64)
        return rev

    def press_out_screen(self, pix_point, **kwargs):
        click_orders = self.__single_click_order(pix_point, z_point=pix_point[2])
        hand_serial_obj_dict.get(self._model.pk).send_out_key_order(click_orders[:2],
                                                                    others_orders=[click_orders[-1]],
                                                                    wait_time=self.speed)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def arm_back_home(self, *args, **kwargs):
        back_order = self.arm_back_home_order()
        for obj_key in hand_serial_obj_dict.keys():
            if obj_key.startswith(self._model.pk):
                serial_obj = hand_serial_obj_dict.get(obj_key)
                for order in back_order:
                    serial_obj.send_single_order(order)
                    serial_obj.recv(buffer_size=32, is_init=True)
        return 0

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
            self.reset_hand(reset_orders=arm_move_position if rotate else arm_wait_position, rotate=rotate, **kwargs)
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
        hand_serial_obj_dict.get(self._model.pk + arm_com).recv(64)
        hand_serial_obj_dict.get(self._model.pk + arm_com_1).recv(64)
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
        left_obj = hand_serial_obj_dict.get(self._model.pk + arm_com)
        right_obj = hand_serial_obj_dict.get(self._model.pk + arm_com_1)

        exec_t1 = threading.Thread(target=left_obj.send_list_order, args=[left_order[0]],
                                   kwargs={"ignore_reset": True})
        exec_t2 = threading.Thread(target=right_obj.send_list_order, args=[right_order[0]],
                                   kwargs={"ignore_reset": True})

        exec_t2.start()
        exec_t1.start()

        while exec_t1.is_alive() or exec_t2.is_alive():
            continue

        exec2_t1 = threading.Thread(target=left_obj.send_list_order, args=[left_order[1:]], )
        exec2_t2 = threading.Thread(target=right_obj.send_list_order, args=[right_order[1:]])

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
        :return:
        """
        if axis[1][0] < axis[0][0] < axis[2][0] < axis[3][0]:
            # 放大，起点x坐标大于终点x坐标
            # 距离最近的是两个起点
            diff_ret = self.judge_diff_x(axis[0][0], axis[2][0])
        elif axis[0][0] < axis[1][0] < axis[3][0] < axis[2][0]:
            # 缩小
            # 距离最近的两个是终点
            diff_ret = self.judge_diff_x(axis[1][0], axis[3][0])
        else:
            raise InvalidCoordinates
        return diff_ret

    @staticmethod
    def judge_diff_x(left_x, right_x):
        # 防撞机制
        # 距离最近的两个点，x坐标差值不得小于安全值
        if abs(left_x - right_x) > DIFF_X:
            return True
        raise InsufficientSafeDistance

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
    def arm_back_home_order():
        return [
            'G01 Z%dF5000 \r\n' % (Z_UP),
            '$H \r\n',
            'G92 X0Y0Z0 \r\n',
            'G90 \r\n',
            arm_wait_position,
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
