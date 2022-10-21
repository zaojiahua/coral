import math
from typing import List

import re

import time

from app.config.setting import CORAL_TYPE
from app.execption.outer.error_code.hands import CrossMax, CoordinateWrongFormat, SideKeyNotFound, \
    ExecContentFormatError, CoordinatesNotReasonable
from app.execption.outer.error_code.adb import NoContent
from app.v1.Cuttle.basic.setting import HAND_MAX_Y, HAND_MAX_X, MOVE_SPEED, Z_MIN_VALUE, get_global_value, \
    X_SIDE_OFFSET_DISTANCE, MAX_SCOPE_5L, MAX_SCOPE_5, MAX_SCOPE_5SE


class DefaultMixin(object):
    # 主要负责机械臂相关方法和位置的转换计算
    def calculate(self, pix_point, absolute=True):
        # pix_point： 像素坐标
        # return： 实际机械臂移动坐标
        # 如果要改变手机位置判断方法，修改此函数
        from app.v1.device_common.device_model import Device
        opt_coordinate = []
        device = Device(pk=self._model.pk)
        if CORAL_TYPE == 4:
            if not (hasattr(self, "w_dpi") and hasattr(self, "h_dpi")):
                self.w_dpi = float(device.x_dpi)
                self.h_dpi = float(device.y_dpi)
            # 实际距离，（已加边框，未加左上角点）
            window_coordinate = [pix_point[0] / self.w_dpi * 2.54 * 10 + float(device.x_border),
                                 pix_point[1] / self.h_dpi * 2.54 * 10 + float(device.y_border)]

            opt_coordinate = [
                round(window_coordinate[0] + get_global_value('m_location')[0], 1),
                round(window_coordinate[1] + get_global_value('m_location')[1], 1)
            ]
        elif math.floor(CORAL_TYPE) == 5:
            opt_coordinate = list(device.get_click_position(pix_point[0],
                                                            pix_point[1],
                                                            pix_point[2] if len(pix_point) > 2 else 0,
                                                            absolute=absolute))

        if opt_coordinate[0] > HAND_MAX_X or opt_coordinate[1] > HAND_MAX_Y:
            raise CrossMax

        return opt_coordinate

    def grouping(self, raw_commend: str) -> (List[int], str):
        speed = MOVE_SPEED
        raw_commend = self._compatible_sleep(raw_commend)
        pix_points = ""
        absolute = True
        if 'taier_swipe' in raw_commend:
            position_args_list = raw_commend.split("swipe")[-1].strip().split(' ')
            try:
                speed = int(position_args_list[4])
            except (IndexError, TypeError):
                pass
            pix_points = [float(i) for i in position_args_list[:4]]
            opt_type = "taier_draw_line"
        elif 'taier' in raw_commend:
            pix_points = [float(i) for i in raw_commend.split("tap")[-1].strip().split(' ')]
            opt_type = "taier_click_center_point"
        elif "tap" in raw_commend:
            pix_points = [float(i) for i in raw_commend.split("tap")[-1].strip().split(' ')]
            opt_type = "click"
            if self.kwargs.get('repeat'):
                opt_type = "repeat_click"
        elif "swipe" in raw_commend:
            position_args_list = raw_commend.split("swipe")[-1].strip().split(' ')
            try:
                speed = int(position_args_list[4])
            except (IndexError, TypeError):
                pass
            pix_points = [float(i) for i in position_args_list[:4]]
            if abs(pix_points[2] - pix_points[0]) + abs(pix_points[3] - pix_points[1]) < 10:
                opt_type = "long_press"
            elif self.kwargs.get('continuous'):
                opt_type = 'continuous_swipe'
            elif self.kwargs.get('trapezoid'):
                opt_type = 'trapezoid_slide'
            elif self.kwargs.get('repeat'):
                opt_type = 'repeat_slide_order'
            elif self.kwargs.get('straight'):
                opt_type = 'straight_swipe'
            else:
                opt_type = "sliding"
        # 下面这堆主要支持机械臂去点击一些固定操作（已经做的adb unit），写的有点难看，有时间可以改成dict的配置形式
        elif "repeat sliding time" in raw_commend:
            speed = int(raw_commend.strip(" ").split(" ")[-1])  # 此时speed存储的是重复次数
            opt_type = 'repeat_sliding'
        elif "repeat click time" in raw_commend:
            speed = int(raw_commend.strip(" ").split(" ")[-1])  # 此时speed存储的是重复次数
            opt_type = "record_repeat_count"
        elif "input keyevent 4" in raw_commend:
            opt_type = "back"
            pix_points = 0
        elif "input keyevent 3" in raw_commend:
            opt_type = "home"
            pix_points = 0
        elif "input keyevent 82" in raw_commend:
            opt_type = "menu"
            pix_points = 0
        elif "long press menu" in raw_commend:
            opt_type = "long_press_menu"
            pix_points = 0
        elif ("press custom-point" in raw_commend) or ("press side" in raw_commend) or (
                "press out-screen" in raw_commend):
            opt_type = "press_custom_point"
            absolute = False
            get_out_key = self.exec_content.split(" ")
            if len(get_out_key) != 4: raise ExecContentFormatError
            out_key = get_out_key[2]
            pix_points = self.cal_press_pix_point(out_key, is_side=False)
            speed = int(get_out_key[3])
        elif 'G01' in raw_commend:
            pix_points = raw_commend
            opt_type = 'rotate'
        elif "armReset" in raw_commend:
            opt_type = "arm_back_home"
        elif 'closeUSBPower' in raw_commend:
            opt_type = "close_usb_power"
        elif "openUSBPower" in raw_commend:
            opt_type = "open_usb_power"
        elif "double hand" in raw_commend and "time" in raw_commend:
            opt_type = "double_hand_swipe"
            speed = int(raw_commend.strip(" ").split(" ")[-1])
        elif "double hand" in raw_commend:
            opt_type = "record_double_hand_point"
            pix_points = [float(i) for i in raw_commend.strip(" ").split(" ")[-8:]]
        else:
            pix_points = [float(i) for i in raw_commend.split("double_point")[-1].strip().split(" ")]
            opt_type = "double_click"
        return pix_points, opt_type, speed, absolute

    def _compatible_sleep(self, exec_content) -> str:
        if "<4ccmd>" in exec_content:
            exec_content = exec_content.replace("<4ccmd>", '')
        if "<sleep>" in exec_content:
            res = re.search("<sleep>(.*?)$", exec_content)
            sleep_time = res.group(1)
            print('--------------即将睡眠：', str(sleep_time))
            time.sleep(float(sleep_time))
            exec_content = exec_content.replace("<sleep>" + sleep_time, "").strip()
        if len(exec_content) <= 1:
            raise NoContent
        return exec_content

    def transform_pix_point(self, k, absolute):
        if isinstance(k, str) or isinstance(k, int):
            # 旋转机械臂
            return k
        if len(k) == 3:
            return self.calculate(k, absolute)
        if len(k) == 8:
            # 双指滑动
            pix_point = [k[0:2], k[2:4], k[4:6], k[6:8]]
            return [self.calculate(i) for i in pix_point]
        if len(k) != 2 and len(k) != 4:
            raise CoordinateWrongFormat
        pix_point = [k] if len(k) == 2 else [k[:2], k[2:]]
        return [self.calculate(i) for i in pix_point]

    def cal_press_pix_point(self, press_key, is_side=True):
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=self._model.pk)
        if press_key not in device_obj.device_config_point.keys():
            raise SideKeyNotFound
        return device_obj.device_config_point[press_key]

    @staticmethod
    def judge_coordinates_reasonable(coordinates, max_x, min_x, min_z):
        # 如果侧边键坐标在屏幕内，超出一定范围，判断不合理
        if coordinates[2] < (min_z + Z_MIN_VALUE):
            raise CoordinatesNotReasonable
            # 侧边键坐标在屏幕外合理
        if coordinates[0] <= min_x or coordinates[0] >= max_x:
            if abs(coordinates[0] - min_x) <= X_SIDE_OFFSET_DISTANCE or abs(
                    max_x - coordinates[0]) <= X_SIDE_OFFSET_DISTANCE:
                return True
        raise CoordinatesNotReasonable

    @staticmethod
    def judge_coordinate_in_arm(point):
        # 判断物理坐标点是否在机械臂范围内
        """
        point: [x, y, z]  物理坐标，单位mm
        5SE, 5, 5L, 5PRO, 5D
        """
        if CORAL_TYPE == 5.2:
            max_scope_x, max_scope_y = MAX_SCOPE_5SE
        elif CORAL_TYPE in [5, 5.4]:
            max_scope_x, max_scope_y = MAX_SCOPE_5
        elif CORAL_TYPE == 5.1:
            max_scope_x, max_scope_y = MAX_SCOPE_5L
        elif CORAL_TYPE == 5.3:
            max_scope_x, max_scope_y = HAND_MAX_X, -HAND_MAX_Y
        else:
            return False

        if point[0] < 0 or point[0] >= max_scope_x or point[1] <= max_scope_y or point[1] > 0:
            return False

        return True

    @staticmethod
    def judge_cross(axis1, axis2):
        """
        该函数用来判断两条线段是否相交
        axis1: [起点x坐标，起点y坐标，终点x坐标，终点y坐标]
        axis2: [起点x坐标，起点y坐标，终点x坐标，终点y坐标]
        """
        point_is_exist = False
        x, y = 0, 0
        x1, y1, x2, y2 = axis1
        x3, y3, x4, y4 = axis2

        if (x2 - x1) == 0:
            k1 = None
            b1 = 0
        else:
            k1 = (y2 - y1) * 1.0 / (x2 - x1)  # 计算k1,由于点均为整数，需要进行浮点数转化
            b1 = y1 * 1.0 - x1 * k1 * 1.0

        if (x4 - x3) == 0:  # L2直线斜率不存在
            k2 = None
            b2 = 0
        else:
            k2 = (y4 - y3) * 1.0 / (x4 - x3)  # 斜率存在
            b2 = y3 * 1.0 - x3 * k2 * 1.0

        if k1 is None:
            if not k2 is None:
                x = x1
                y = k2 * x1 + b2
                point_is_exist = True
        elif k2 is None:
            x = x3
            y = k1 * x3 + b1
        elif not k2 == k1:
            x = (b2 - b1) * 1.0 / (k1 - k2)
            y = k1 * x * 1.0 + b1 * 1.0
            point_is_exist = True

        return point_is_exist, [x, y]


class CameraMixin(DefaultMixin):
    def calculate(self, pix_point):
        pass
