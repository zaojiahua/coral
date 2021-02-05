import time

from app.v1.Cuttle.basic.calculater_mixin.default_calculate import DefaultMixin
from app.v1.Cuttle.basic.hand_serial import HandSerial
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.setting import HAND_MAX_Y, HAND_MAX_X, SWIPE_TIME, Z_START, Z_DOWN, Z_UP, MOVE_SPEED, \
    hand_serial_obj_dict, normal_result


def hand_init(arm_com_id, device_obj):
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
        "G92 X0Y0Z0 \r\n",
        "G90 \r\n"
    ]
    for g_orders in hand_reset_orders:
        hand_serial_obj.send_single_order(g_orders)
        hand_serial_obj.recv(buffer_size=64)
    return 0


def rotate_hand_init(arm_com_id, device_obj):
    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id=arm_com_id)
    hand_serial_obj_dict[device_obj.pk] = hand_serial_obj
    hand_reset_orders = [
        "$G \r\n",
        "$x \r\n",
        "G92 X0Y0Z0 \r\n",
        "G90 \r\n",
        "G01 X0Y35Z0F1000 \r\n"
    ]
    for g_orders in hand_reset_orders:
        hand_serial_obj.send_single_order(g_orders)
        hand_serial_obj.recv(buffer_size=64)
    return 0


class HandHandler(Handler, DefaultMixin):

    def __init__(self,*args,**kwargs):
        super(HandHandler, self).__init__(*args,**kwargs)
        self.ignore_reset = False

    def before_execute(self):
        pix_points, opt_type = self.grouping(self.exec_content)
        self.exec_content = self.transform_pix_point(pix_points)
        self.func = getattr(self, opt_type)
        return normal_result

    def click(self, axis_list, **kwargs):
        # 单击，支持连续单击，例如：拨号
        click_orders = self.__list_click_order(axis_list)
        hand_serial_obj_dict.get(self._model.pk).send_list_order(click_orders)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def double_click(self, double_axis, **kwargs):
        # 双击，在同一个点快速点击两次
        double_click_orders = self.__double_click_order(double_axis)
        hand_serial_obj_dict.get(self._model.pk).send_list_order(double_click_orders)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def long_press(self, start_point, swipe_time=SWIPE_TIME, **kwargs):
        # 长按
        long_click_orders = self.__single_click_order(start_point[0])
        hand_serial_obj_dict.get(self._model.pk).send_list_order(long_click_orders[:2], wait=True)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def sliding(self, point, swipe_time=SWIPE_TIME, **kwargs):
        # TODO 控制滑动时间,增加移动速度的换算
        sliding_order = self.__sliding_order(point[0], point[1])
        hand_serial_obj_dict.get(self._model.pk).send_list_order(sliding_order)
        return hand_serial_obj_dict.get(self._model.pk).recv()

    def reset_hand(self):
        hand_reset_orders = "G01 X10Y-120Z12F12000 \r\n"
        hand_serial_obj_dict.get(self._model.pk).send_single_order(hand_reset_orders)
        hand_serial_obj_dict.get(self._model.pk).recv()
        return 0

    def rotate(self, commend):
        from app.v1.device_common.device_model import Device
        rotate_camera = Device(pk=self._model.pk).has_rotate_camera
        if rotate_camera is False:
            return -9
        hand_serial_obj_dict.get(self._model.pk).send_single_order(commend)
        hand_serial_obj_dict.get(self._model.pk).recv()
        self.ignore_reset = True
        return 0



    def after_unit(self):
        if self.ignore_reset is False:
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
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_UP, MOVE_SPEED),
            'G01 Z%dF%d \r\n' % (Z_DOWN, MOVE_SPEED),
            'G01 Z%dF%d \r\n' % (Z_UP, MOVE_SPEED)
        ]

    @staticmethod
    def __double_click_order(axis):
        axis_x, axis_y = axis
        if axis_x > HAND_MAX_X or axis_y > HAND_MAX_X:
            return {"error:Invalid axis_Point"}
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (axis_x, axis_y, Z_START, MOVE_SPEED),
            'G01 Z%dF%d \r\n' % (Z_DOWN, MOVE_SPEED),
            'G01 Z%dF%d \r\n' % (Z_UP, MOVE_SPEED),
            'G01 Z%dF%d \r\n' % (Z_DOWN, MOVE_SPEED),
            'G01 Z%dF%d \r\n' % (Z_UP, MOVE_SPEED),
        ]

    # TODO 滑动起止点是否超过操作台范围
    @staticmethod
    def __sliding_order(start_point, end_point):
        # 点击的起始点
        start_x, start_y = start_point
        end_x, end_y = end_point
        # 从下往上   [500,800] -> [500, 200]
        if (start_x == end_x) and (start_y > end_y):
            end_y = start_x - 40 if (start_y - end_y) > 40 else end_y
        return [
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_START, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (start_x, start_y, Z_DOWN, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fF%d \r\n' % (end_x, end_y, MOVE_SPEED),
            'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (end_x, end_y, Z_UP, MOVE_SPEED),
        ]


if __name__ == '__main__':

    hand_serial_obj = HandSerial(timeout=2)
    hand_serial_obj.connect(com_id="COM7")
    hand_reset_orders = ['G01 X70.0Y-176.0Z8F15000 \r\n', 'G01 Z0F15000 \r\n', "G01 X10Y-120Z8F15000 \r\n"]
    init = [
        "$x \r\n",
        "$h \r\n",
        "G92 X0Y0Z0 \r\n",
        "G90 \r\n"
    ]
    for g_orders in init:
        hand_serial_obj.send_single_order(g_orders)
        hand_serial_obj.recv(buffer_size=64)

    for i in range(5):
        for g_orders in hand_reset_orders:
            a = time.time()
            hand_serial_obj.send_single_order(g_orders)
            hand_serial_obj.recv()
            print(time.time() - a)
