from typing import List

import re

import time

from app.execption.outer.error_code.hands import CrossMax, CoordinateWrongFormat
from app.execption.outer.error_code.adb import NoContent
from app.v1.Cuttle.basic.setting import HAND_MAX_Y, HAND_MAX_X, m_location


class DefaultMixin(object):
    # 主要负责机械臂相关方法和位置的转换计算

    def calculate(self, pix_point):
        # pix_point： 像素坐标
        # return： 实际机械臂移动坐标
        # 如果要改变手机位置判断方法，修改此函数
        from app.v1.device_common.device_model import Device
        device = Device(pk=self._model.pk)

        if not (hasattr(self, "w_dpi") and hasattr(self, "h_dpi")):
            self.w_dpi = float(device.x_dpi)
            self.h_dpi = float(device.y_dpi)
        # 实际距离，（已加边框，未加左上角点）
        window_coordinate = [pix_point[0] / self.w_dpi * 2.54 * 10 + float(device.x_border),
                             pix_point[1] / self.h_dpi * 2.54 * 10 + float(device.y_border)]

        opt_coordinate = [
            round(window_coordinate[0] + m_location[0], 1),
            round(window_coordinate[1] + m_location[1], 1)
        ]
        if opt_coordinate[0] > HAND_MAX_X or opt_coordinate[1] > HAND_MAX_Y:
            raise CrossMax
        return opt_coordinate

    def grouping(self, raw_commend) -> (List[int], str):
        raw_commend = self._compatible_sleep(raw_commend)
        if "tap" in raw_commend:
            pix_points = [float(i) for i in raw_commend.split("tap")[-1].strip().split(' ')]
            opt_type = "click"
        elif "swipe" in raw_commend:
            pix_points = [float(i) for i in (raw_commend.split("swipe")[-1].strip().split(' ')[:4])]
            if abs(pix_points[2] - pix_points[0]) + abs(pix_points[3] - pix_points[1]) < 10:
                opt_type = "long_press"
            elif hasattr(self, 'continuous') and self.continuous:
                opt_type = 'continuous_swipe'
            else:
                opt_type = "sliding"
        elif 'G01' in raw_commend:
            pix_points = raw_commend
            opt_type = 'rotate'
        else:
            pix_points = [int(i) for i in raw_commend.strip().split(' ')]
            opt_type = "double_click"
        return pix_points, opt_type

    def _compatible_sleep(self, exec_content):
        if "<4ccmd>" in exec_content:
            exec_content = exec_content.replace("<4ccmd>", '')
        if "<sleep>" in exec_content:
            res = re.search("<sleep>(.*?)$", exec_content)
            sleep_time = res.group(1)
            time.sleep(float(sleep_time))
            exec_content = exec_content.replace("<sleep>" + sleep_time, "").strip()
        if len(exec_content) <= 1:
            raise NoContent
        return exec_content

    def transform_pix_point(self, k):
        if isinstance(k, str):
            # 旋转机械臂
            return k
        if len(k) != 2 and len(k) != 4:
            raise CoordinateWrongFormat
        pix_point = [k] if len(k) == 2 else [k[:2], k[2:]]
        return [self.calculate(i) for i in pix_point]


class CameraMixin(DefaultMixin):
    def calculate(self, pix_point):
        pass
