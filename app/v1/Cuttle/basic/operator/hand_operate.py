import re
import time

import numpy as np

from app.config.setting import CORAL_TYPE
from app.config.url import device_url, phone_model_url
from app.execption.outer.error_code.hands import KeyPositionUsedBeforesSet
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.default_calculate import DefaultMixin
from app.v1.Cuttle.basic.hand_serial import HandSerial
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.setting import HAND_MAX_Y, HAND_MAX_X, SWIPE_TIME, Z_START, Z_DOWN, Z_UP, MOVE_SPEED, \
    hand_serial_obj_dict, normal_result, trapezoid, wait_bias, arm_default, arm_wait_position, wait_time, \
    arm_move_position


def hand_init(arm_com_id, device_obj, **kwargs):
    # 龙门架机械臂初始化
    """
    1. 解锁机械臂，并将机械臂移动至Home位置
    2. 设置坐标模式为绝对值模式
    3. 设置HOME点为操作原点
    :return:
    """
    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id=arm_com_id)
    hand_serial_obj_dict[device_obj.pk] = hand_serial_obj
    hand_reset_orders = [
        "$x \r\n",
        "$h \r\n",
        f"G92 X0Y0Z{Z_UP} \r\n",
        "G90 \r\n",
        arm_wait_position
    ]
    for g_orders in hand_reset_orders:
        hand_serial_obj.send_single_order(g_orders)
        hand_serial_obj.recv(buffer_size=64)
    return 0


def rotate_hand_init(arm_com_id, device_obj, **kwargs):
    # 旋转机械臂初始化
    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id=arm_com_id)
    hand_serial_obj_dict[device_obj.pk] = hand_serial_obj
    hand_reset_orders = [
        "$G \r\n",
        "$x \r\n",
        "G92 X0Y0Z0F15000 \r\n",
        "G90 \r\n",
        arm_default
    ]
    for g_orders in hand_reset_orders:
        hand_serial_obj.send_single_order(g_orders)
        response = hand_serial_obj.recv(buffer_size=64)
    return 0


class HandHandler(Handler, DefaultMixin):
    before_match_rules = {
        # 用在执行之前，before_execute中针对不同方法正则替换其中的相对坐标到绝对坐标
        "input tap": "_relative_point",
        "input swipe": "_relative_swipe",
        "double_point": "_relative_double_point",
    }

    def __init__(self, *args, **kwargs):
        super(HandHandler, self).__init__(*args, **kwargs)
        self.ignore_reset = False

    def before_execute(self):
        # 先转换相对坐标到绝对坐标
        for key, value in self.before_match_rules.items():
            if key in self.exec_content:
                getattr(self, value)()
        # 根据adb指令中的关键词dispatch到对应机械臂方法,pix_points为adb模式下的截图中的像素坐标
        pix_points, opt_type, self.speed = self.grouping(self.exec_content)
        # 根据截图中的像素坐标，根据dpi和起始点坐标，换算到物理距离中毫米为单位的坐标
        self.exec_content = self.transform_pix_point(pix_points)
        # 龙门架机械臂self.exec_content是列表（放点击的坐标），所以会找self.func这个方法来执行（写在基类的流程中）
        # 旋转机械臂self.exec_content是字符串命令，所以会找self.str_func这个方法来执行
        self.func = getattr(self, opt_type)
        return normal_result

    def click(self, axis_list, **kwargs):
        # 单击，支持连续单击，例如：拨号
        click_orders = self.__list_click_order(axis_list)
        ignore_reset = self.kwargs.get("ignore_arm_reset")
        self.ignore_reset = ignore_reset
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders, ignore_reset=ignore_reset)
        result = hand_serial_obj_dict.get(self._model.pk).recv()
        if ignore_reset != True:
            time.sleep(wait_time)
        return result

    def double_click(self, double_axis, **kwargs):
        # 双击，在同一个点快速点击两次
        double_click_orders = self.__double_click_order(double_axis[0])
        hand_serial_obj_dict.get(self._model.pk).send_list_order(double_click_orders)
        time.sleep(wait_time)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def long_press(self, start_point, swipe_time=SWIPE_TIME, **kwargs):
        # 长按
        long_click_orders = self.__single_click_order(start_point[0])
        hand_serial_obj_dict.get(self._model.pk).send_list_order(long_click_orders[:2],
                                                                 other_orders=[long_click_orders[-1]],
                                                                 wait=True, wait_time=self.speed)
        time.sleep(wait_time)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def sliding(self, point, swipe_time=SWIPE_TIME, **kwargs):
        # # 滑动，self.speed是滑动速度
        # 2021.12.17 滑动，self.speed是滑动时间
        swipe_distance = np.hypot(point[1][0] - point[0][0], point[1][1] - point[0][1])
        cal_swipe_speed = swipe_distance / (self.speed * 0.00002)
        swipe_speed = cal_swipe_speed if cal_swipe_speed < 10000 else 10000

        sliding_order = self.__sliding_order(point[0], point[1], swipe_speed)
        hand_serial_obj_dict.get(self._model.pk).send_list_order(sliding_order)
        # time.sleep(wait_time)
        if swipe_speed == 10000:
            self.ignore_reset = True

        result = hand_serial_obj_dict.get(self._model.pk).recv()
        # ensure low speed swipe can end with true-time(get sleep time according to swipe distance and speed)
        if swipe_speed < 2000:
            distance = np.hypot(point[1][0] - point[0][0], point[1][1] - point[0][1]) * 50
            time.sleep((distance / self.speed) + 0.5)
        return result

    def trapezoid_slide(self, point, **kwargs):
        # 用力滑动，会先计算滑动起始/终止点的  同方向延长线坐标，并做梯形滑动
        sliding_order = self.__sliding_order(point[0], point[1], self.speed, normal=False)
        hand_serial_obj_dict.get(self._model.pk).send_list_order(sliding_order)
        if self.speed < 2000:
            distance = np.hypot(point[1][0] - point[0][0], point[1][1] - point[0][1]) * 50
            time.sleep((distance / self.speed) + 1.5)
        time.sleep(3.5)  # 因为用力滑动会有惯性,sleep3确保动作执行完成
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def reset_hand(self, hand_reset_orders=arm_wait_position, **kwargs):
        # 恢复手臂位置 可能是龙门架也可能是旋转机械臂
        self._model.logger.info(f"reset hand order:{hand_reset_orders}")
        hand_serial_obj_dict.get(self._model.pk).send_single_order(hand_reset_orders)
        hand_serial_obj_dict.get(self._model.pk).recv()
        time.sleep(wait_time)
        return 0

    def continuous_swipe(self, commend, **kwargs):
        # 连续滑动方法，多次滑动之间不抬起，执行完不做等待
        sliding_order = self._sliding_contious_order(commend[0], commend[1], kwargs.get('index', 0),
                                                     kwargs.get('length', 0))
        hand_serial_obj_dict.get(self._model.pk).send_list_order(sliding_order, ignore_reset=True)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def back(self, _, **kwargs):
        # 按返回键，需要在5#型柜 先配置过返回键的位置
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        click_orders = self.__single_click_order(self.calculate((device_obj.back_x, device_obj.back_y)))
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders)
        result = hand_serial_obj_dict.get(self._model.pk).recv()
        time.sleep(wait_time)
        return result

    def double_back(self, _, **kwargs):
        # 双击返回键  同5#型柜使用
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        click_orders = self.__double_click_order(self.calculate((device_obj.back_x, device_obj.back_y)))
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders)
        result = hand_serial_obj_dict.get(self._model.pk).recv()
        time.sleep(wait_time)
        return result

    def home(self, _, **kwargs):
        # 点击桌面键 5#型柜使用
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        click_orders = self.__single_click_order(self.calculate((device_obj.home_x, device_obj.home_y)))
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders)
        result = hand_serial_obj_dict.get(self._model.pk).recv()
        time.sleep(wait_time)
        return result

    def menu(self, _, **kwargs):
        # 点击菜单键 5#型柜使用
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        click_orders = self.__single_click_order(self.calculate((device_obj.menu_x, device_obj.menu_y)))
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders)
        result = hand_serial_obj_dict.get(self._model.pk).recv()
        time.sleep(wait_time)
        return result

    def long_press_menu(self, _, **kwargs):
        # 长按菜单键 5#型柜使用
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        click_orders = self.__single_click_order(self.calculate((device_obj.menu_x, device_obj.menu_y)))
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders[:2],
                                                                 other_orders=[click_orders[-1]],
                                                                 wait=True)
        result = hand_serial_obj_dict.get(self._model.pk).recv()
        time.sleep(wait_time)
        return result

    def power(self, _, **kwargs):
        # 按电源键，5#柜规划，还未实现
        pass

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
        # 旋转机械臂执行的方法
        from app.v1.device_common.device_model import Device
        move = False
        sleep_time = 0
        if Device(pk=self._model.pk).has_rotate_arm is False:
            return -9
        if '<rotateSleep>' in commend:
            # 长按的等待操作，等待输入的时间+wait_bias时间。
            res = re.search("<rotateSleep>(.*?)$", commend)
            sleep_time = res.group(1)
            commend = commend.replace("<rotateSleep>" + sleep_time, "")
        if '<move>' in commend:
            # 归位操作，用于长按电源后归reset位置。
            commend = commend.replace('<move>', "")
            move = True
        hand_serial_obj_dict.get(self._model.pk).send_single_order(commend)
        # hand_serial_obj_dict.get(self._model.pk).recv()
        if float(sleep_time) > 0:
            time.sleep(float(sleep_time) + wait_bias)
        if move:
            self.reset_hand(hand_reset_orders=arm_move_position)
        hand_serial_obj_dict.get(self._model.pk).recv()
        self.ignore_reset = True
        return 0

    def rotate(self, commend):
        return self.str_func(commend)

    def after_unit(self):
        # unit执行完 5型柜执行移开的操作，防止长时间遮挡摄像头
        if self.ignore_reset is False and CORAL_TYPE == 5:
            self.reset_hand()

    # TODO 怎样处理如果传入点中有一个或多个计算出的坐标超过操作台范围
    def __list_click_order(self, axis_list):
        click_orders = []
        for axis in axis_list:
            click_order = self.__single_click_order(axis)
            click_orders.extend(click_order)
        return click_orders

    @staticmethod
    def __single_click_order(axis):
        axis_x, axis_y = axis
        if axis_x > HAND_MAX_X or axis_y > HAND_MAX_Y:
            return {"error:Invalid Pix_Point"}
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN + 5, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN, MOVE_SPEED),
            # 'G01 Z%dF%d \r\n' % (Z_DOWN, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_UP, MOVE_SPEED),
            # 'G01 Z%dF%d \r\n' % (Z_UP, MOVE_SPEED)
        ]

    @staticmethod
    def _press_button_order(axis):
        axis_x, axis_y = axis
        if axis_x > HAND_MAX_X or axis_y > HAND_MAX_Y:
            return {"error:Invalid Pix_Point"}
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN + 5, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN, MOVE_SPEED),
            # 'G01 Z%dF%d \r\n' % (Z_DOWN, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_UP, MOVE_SPEED),
            # 'G01 Z%dF%d \r\n' % (Z_UP, MOVE_SPEED)
        ]

    @staticmethod
    def __double_click_order(axis):
        axis_x, axis_y = axis
        if axis_x > HAND_MAX_X or axis_y > HAND_MAX_X:
            return {"error:Invalid axis_Point"}
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN + 5, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_UP, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_DOWN, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_UP, MOVE_SPEED),

        ]

    # TODO 滑动起止点是否超过操作台范围
    @staticmethod
    def __sliding_order(start_point, end_point, speed=MOVE_SPEED, normal=True):
        # 点击的起始点
        start_x, start_y = start_point
        end_x, end_y = end_point
        # 从下往上   [500,800] -> [500, 200]
        # if (start_x == end_x) and (start_y > end_y):
        #     end_y = start_x - 40 if (start_y - end_y) > 40 else end_y
        if normal:
            commend_list = [
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_DOWN + 5, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_DOWN - 1, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fF%d \r\n' % (end_x, end_y, speed),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (end_x, end_y, Z_UP, MOVE_SPEED),
            ]
            # if speed <= 500:
            #     commend_list.insert(2, "<SLEEP>")
            return commend_list
        else:
            x1 = min(max(start_x - (end_x - start_x) * 10 / np.abs(end_x - start_x) * trapezoid, 0), 120)
            y1 = min(max(start_y - (end_y - start_y) * 10 / np.abs((end_y - start_y)) * trapezoid, 0), 150)
            x4 = min(max(end_x + (end_x - start_x) * trapezoid, 0), 150)
            y4 = min(max(end_y + (end_y - start_y) * trapezoid, 0), 150)
            return [
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x1, y1, Z_START, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_DOWN - 1, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (end_x, end_y, Z_DOWN + 3, speed),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x4, y4, Z_UP, MOVE_SPEED),
            ]

    def _sliding_contious_order(self, start_point, end_point, commend_index, commend_length):
        start_x, start_y = start_point
        end_x, end_y = end_point
        # 连续滑动保证动作无偏差
        from app.v1.Cuttle.basic.setting import last_swipe_end_point
        # 在4,5 型号柜1代表毫米，其他型柜15代表像素，所以这里做区分。
        th = 15 if CORAL_TYPE < 4 else 1
        # 如果前一滑动的终止点和下一次滑动的起始点很接近，我们认为就是要连续滑动，直接把其赋值为相同点。并且每次都缓存此次的终止点做下次对比
        if np.abs(start_x - last_swipe_end_point[0]) < th and np.abs(start_y - last_swipe_end_point[1]) < th:
            start_x, start_y = last_swipe_end_point
        last_swipe_end_point[0] = end_x
        last_swipe_end_point[1] = end_y
        # 首次动作有移动和下压动作
        if commend_index == 0:
            return [
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_START, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_DOWN, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED)
            ]
        elif commend_index + 1 != commend_length:  # 后面动作只有滑动
            return [
                'G01 X%0.1fY-%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED)
            ]
        else:
            return [
                'G01 X%0.1fY-%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED),
                'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (end_x, end_y, Z_START, MOVE_SPEED)
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
