import logging
import math
import os.path
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback

import cv2
import numpy as np
from PIL import Image
from flask import request, jsonify, Response
from flask.views import MethodView
from serial import SerialException

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import SUCCESS_PIC_NAME, FAIL_PIC_NAME, LEAVE_PIC_NAME, PANE_LOG_NAME, DEVICE_BRIGHTNESS, \
    arm_com_1, CORAL_TYPE, arm_com, arm_com_1_sensor, IP_FILE_PATH, arm_com_1_jaw
from app.execption.outer.error_code.camera import PerformancePicNotFound, CoordinateConvertFail, CoordinateConvert, \
    MergeShapeNone
from app.execption.outer.error_code.hands import UsingHandFail, CoordinatesNotReasonable, TcabNotAllowExecThisUnit, \
    CrossMax
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.hand_serial import controlUsbPower
from app.v1.Cuttle.basic.component.hand_component import read_z_down_from_file, read_wait_position, get_wait_position
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import camera_start
from app.v1.Cuttle.basic.operator.hand_operate import hand_init, rotate_hand_init, HandHandler, judge_start_x, \
    pre_point, sensor_init, get_hand_serial_key
from app.v1.Cuttle.basic.operator.jaw_operate import jaw_init
from app.v1.Cuttle.basic.calculater_mixin.default_calculate import DefaultMixin
from app.v1.Cuttle.basic.operator.handler import Dummy_model
from app.v1.Cuttle.basic.setting import hand_serial_obj_dict, rotate_hand_serial_obj_dict, get_global_value, \
    MOVE_SPEED, X_SIDE_OFFSET_DISTANCE, PRESS_SIDE_KEY_SPEED, set_global_value, \
    COORDINATE_CONFIG_FILE, MERGE_IMAGE_H, Z_UP, COORDINATE_POINT_FILE, REFERENCE_VALUE, CLICK_TIME, ACCELERATION_TIME, \
    HAND_MAX_X, Z_POINT_FILE, WAIT_POSITION_FILE
from app.v1.Cuttle.macPane.schema import PaneSchema, OriginalPicSchema, CoordinateSchema, ClickTestSchema
from app.v1.Cuttle.network.network_api import unbind_spec_ip
from app.v1.device_common.device_model import Device
from app.v1.tboard.views.get_dut_progress import get_dut_progress_inner
from app.v1.tboard.views.stop_specific_device import stop_specific_device_inner
from redis_init import redis_client

import copy

from app.v1.Cuttle.basic.setting import COMPUTE_M_LOCATION
from app.v1.Cuttle.basic.common_utli import hand_move_times

ip = copy.copy(HOST_IP)
logger = logging.getLogger(PANE_LOG_NAME)


def pic_push(device_object, pic_name="success.png"):
    pic_ip = ip.replace("100", "138") if sys.platform.startswith("win") else ip
    jsdata = {
        "execBlockName": "set_config_success",
        "ip_address": device_object.ip_address,
        "device_label": device_object.device_label,
        "execCmdList": [
            "adb -s " + device_object.connect_number + f" shell am start -a android.intent.action.VIEW -d http://{pic_ip}:5000/static/{pic_name}"]

    }
    if pic_name == LEAVE_PIC_NAME:
        jsdata["execCmdList"].append(f"adb disconnect {device_object.ip_address}")
    pic_push_result = UnitFactory().create("AdbHandler", jsdata)
    logger.info(f"picture push result for {pic_name}'s result :{pic_push_result}")


def update_phone_model():
    data = request.get_json()
    for device_obj in Device.all():
        if device_obj.phone_model_name == data.get("phone_model_name"):
            device_obj._update_attr_from_device(**data)
    return jsonify({"status": "success"}), 200


class PaneUpdateView(MethodView):
    def post(self):
        data = request.get_json()
        device_object = Device(pk=data.get("device_label"))
        try:
            device_object.update_attr(**data, avoid_push=True)
            pic_push(device_object, pic_name=SUCCESS_PIC_NAME)
            return jsonify({"status": "success"}), 200
        except Exception as e:
            pic_push(device_object, pic_name=FAIL_PIC_NAME)
            return jsonify({"status": "fail"}), 400


class PaneDeleteView(MethodView):
    def post(self):
        # 先停止正在运行的tboard
        data = request.get_json()
        if get_dut_progress_inner(data.get("device_label")) == {"status": "busy"}:
            res = stop_specific_device_inner(data.get("device_label"))
            if isinstance(res, Exception):
                return jsonify({"wrong": "stop device fail"}), 400
        device_object = Device(pk=data.get("device_label"))

        try:
            # 推送结束图片
            if device_object.ip_address != "0.0.0.0":
                pic_push(device_object, pic_name=LEAVE_PIC_NAME)
            if device_object.has_rotate_arm:
                # todo  clear used list when only one arm for one server
                self._reset_arm(device_object)
            if device_object.has_arm:
                try:
                    hand_serial_obj = hand_serial_obj_dict[get_hand_serial_key(device_object.pk, arm_com)]
                    hand_serial_obj.close()
                except KeyError:
                    # 多见与机柜型号填写有误时
                    pass
            if device_object.has_camera:
                redis_client.set("g_bExit", "1")
        except Exception:
            print('移除相关资源的时候发生异常')
            traceback.print_exc()

        from app.v1.Cuttle.basic.setting import hand_used_list
        hand_used_list.clear()
        # 移除redis中缓存
        device_object.simple_remove()
        if data.get("assistance_ip_address"):
            h = AdbHandler(model=Dummy_model(False, "dummy", setup_logger(f'temp', f'temp.log')))
            for ip in data.get("assistance_ip_address"):
                h.disconnect(ip)
        # 解除路由器IP绑定 start after jsp finished
        if ADB_TYPE == 0:
            res = unbind_spec_ip(data.get("ip_address"))
            # 此处注释了路由绑定的验证，因为有很多款不同路由，现在状态不能保证成功
            # if res != 0:
            #     raise DeviceBindFail
        return jsonify({"status": "success"}), 200

    def _reset_arm(self, device_object):
        try:
            hand_serial_obj = rotate_hand_serial_obj_dict[device_object.pk]
            hand_serial_obj.send_single_order("G01 X0Y0Z0F1000 \r\n")
            hand_serial_obj.recv(buffer_size=64)
            hand_serial_obj.close()
        except SerialException as e:
            return


class PaneAssisDeleteView(MethodView):
    def post(self):
        # 先停止对应主机的tboard
        data = request.get_json()
        if get_dut_progress_inner(data.get("relative_device_label")) == {"status": "busy"}:
            res = stop_specific_device_inner(data.get("relative_device_label"))
            if isinstance(res, Exception):
                return jsonify({"wrong": "stop device fail"}), 400
        h = AdbHandler(model=Dummy_model(False, "dummy", setup_logger(f'temp', f'temp.log')))
        h.disconnect(ip=data.get("ip_address"))
        return jsonify({"status": "success"}), 200


class PaneFunctionView(MethodView):
    def get(self):
        schema = PaneSchema()
        return schema.load(request.args)


class PaneOriginalView(MethodView):
    def get(self):
        schema = OriginalPicSchema()
        return schema.load(request.args)


class PerformancePictureView(MethodView):
    def get(self):
        path = request.args.get("path")
        try:
            f = open(path, "rb")
            image = f.read()
        except FileNotFoundError:
            raise PerformancePicNotFound
        return Response(image, mimetype="image/jpeg")


class PaneConfigView(MethodView):

    def init_bright(self, device_label):
        ip = Device(pk=device_label).ip_address
        cmd = f"adb -s {ip}:5555 shell echo {DEVICE_BRIGHTNESS} >/sys/class/leds/lcd-backlight/brightness"
        jsdata = {
            "execBlockName": "init brightness",
            "ip_address": ip,
            "device_label": device_label,
            "execCmdList": ["<sleep>0.5", cmd]
        }
        adjust_brightness_result = UnitFactory().create("AdbHandler", jsdata)

    @staticmethod
    def hardware_init(port, device_label, rotate=False):
        device_object = Device(pk=device_label)
        if rotate is True:
            function, attribute = (rotate_hand_init, "has_rotate_arm")
        elif port.split("/")[-1].isdigit():
            function, attribute = (camera_start, "has_camera")
        # 电爪
        elif port.startswith('/dev/arm_jaw_'):
            com_index = arm_com_1_jaw.split('_')[-1]
            function, attribute = (jaw_init, "has_jaw_" + com_index)
        elif port.startswith('/dev/arm_jaw'):
            function, attribute = (jaw_init, 'has_jaw')
        # 传感器
        elif port.startswith('/dev/arm_sensor_'):
            com_index = arm_com_1_sensor.split('_')[-1]
            function, attribute = (sensor_init, "has_sensor_" + com_index)
        # or是针对win的条件，方便测试
        elif port.startswith('/dev/arm_sensor') or port == 'COM4':
            function, attribute = (sensor_init, 'has_sensor')
        elif port.startswith('/dev/arm_'):
            com_index = arm_com_1.split('_')[-1]
            function, attribute = (hand_init, "has_arm_" + com_index)
        else:
            function, attribute = (hand_init, "has_arm")
            controlUsbPower(status='init')
        setattr(device_object, attribute, True)
        return function, device_object, attribute


class PaneBorderView(MethodView):
    def post(self):
        schema = CoordinateSchema()
        return schema.load(request.get_json())


class AutoPaneBorderView(MethodView):
    def post(self):
        if not request.files.get("rawImage"):
            return jsonify({"fail": "can not get raw image"}), 400
        image = Image.open(request.files.get("rawImage"))  # 720*1280*3
        src = np.array(image)
        point = self.get_suitable_area(src, 30)
        if point is None:
            return jsonify(
                {"status": "can not find suitable area, please make sure phone is showing a light page"}), 400
        else:
            return jsonify({"upper_left_x": int(point[0][0]),
                            "upper_left_y": int(point[0][1]),
                            "under_right_x": int(point[3][0]),
                            "under_right_y": int(point[3][1]),
                            }), 200

    @staticmethod
    def get_suitable_area(src, thresh):
        kernel = np.uint8(np.ones((3, 3)))
        src = cv2.erode(src, kernel, iterations=2)
        src = cv2.dilate(src, kernel, iterations=2)
        gray = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY)
        ret, binary = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
        image, contours, hierarchy = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        box_list = []
        for contour in contours:
            rect = cv2.minAreaRect(contour[:, 0, :])
            box = cv2.boxPoints(rect)
            area = int(rect[1][1]) * int(rect[1][0])
            if area <= 50000:
                continue
            box_list.append((box, area))
        box_list.sort(key=lambda x: x[1], reverse=True)
        try:
            point = box_list[0][0].tolist()
            point.sort(key=lambda x: x[0] + x[1])
        except IndexError:
            pass

        return point


class FilePushView(MethodView):
    def post(self):
        try:
            file = request.files.get("image")
            name = request.form.to_dict().get("name")
            file.save(name)
            subproc = subprocess.Popen("adb devices", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            restr = subproc.communicate()[0]
            response = restr.strip().decode()
            ip_list = []
            for i in response.split("\n")[1:]:
                item = i.split("\t")[0]
                if "." in item:
                    ip_list.append(item)
            for ip in ip_list:
                subproc = subprocess.Popen(f"adb -s {ip} push {name} /sdcard/DCIM/Screenshots/{name} ",
                                           shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                restr = subproc.communicate()[0]
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            return jsonify({"fail": repr(e)}), 400


# 测试点击
class PaneClickTestView(MethodView):
    """
    支持Pane界面的：
        测试点击
        测试点击多次（click_count）
        停止正在进行的【测试点击多次】线程（stop_loop_flag）

    如果发过来的请求时测试点击，那么先判断机械臂是否在使用，则返回错误码
    如果发过来的请求中包含stop_loop_flag，

    """

    def post(self):
        random_dir = str(random.randint(0, 100))
        if not os.path.exists(random_dir):
            os.mkdir(random_dir)
        fs = request.files.getlist('img')
        for f in fs:
            f.save(os.path.join(random_dir, f.filename))

        schema = ClickTestSchema()
        request_data = request.form.to_dict()
        schema.load(request_data)

        device_label = request_data.get("device_label")
        device_obj = Device(pk=device_label)

        device_point = [int(request_data.get('inside_upper_left_x')),
                        int(request_data.get('inside_upper_left_y')),
                        int(request_data.get('inside_under_right_x')),
                        int(request_data.get('inside_under_right_y'))]
        click_x, click_y, click_z = device_obj.get_click_position(request_data.get('x'),
                                                                  request_data.get('y'),
                                                                  request_data.get('z'),
                                                                  device_point)

        # 获取执行动作需要的信息
        try:
            exec_serial_obj, orders, exec_action = self.get_exec_info(click_x, click_y, click_z, device_label,
                                                                      roi=device_point)
        except TcabNotAllowExecThisUnit:
            return jsonify(dict(error_code=TcabNotAllowExecThisUnit.error_code,
                                description=TcabNotAllowExecThisUnit.description))
        except CoordinatesNotReasonable:
            return jsonify(dict(error_code=CoordinatesNotReasonable.error_code,
                                description=CoordinatesNotReasonable.description))

        # 判断机械臂状态是否在执行循环
        if not get_global_value("click_loop_stop_flag"):
            # 机械臂状态running,且有stop_loop_flag标志值，需要停止机械臂正在执行的动作
            if request_data.get("stop_loop_flag"):
                set_global_value("click_loop_stop_flag", True)
                while not exec_serial_obj.check_hand_status():
                    time.sleep(0.2)
                shutil.rmtree(random_dir)
                return jsonify(dict(error_code=0))
            else:
                shutil.rmtree(random_dir)
                return jsonify(dict(error_code=UsingHandFail.error_code,
                                    description=UsingHandFail.description))

        # 判断是否执行测试点击多次
        if request_data.get("click_count"):
            set_global_value("click_loop_stop_flag", False)
            exec_t1 = threading.Thread(target=self.exec_action_loop,
                                       args=[exec_serial_obj, orders, exec_action, int(request_data.get("click_count")),
                                             random_dir]
                                       )
            exec_t1.start()
            return jsonify(dict(error_code=0))
        else:
            self.exec_hand_action(exec_serial_obj, orders, exec_action)
        shutil.rmtree(random_dir)
        return jsonify(dict(error_code=0))

    @staticmethod
    def get_exec_info(click_x, click_y, click_z, device_label, roi=None, is_normal_speed=False):
        """
        return: serial_obj, orders
        """
        is_left_side = False
        location = get_global_value("m_location")
        device_obj = Device(pk=device_label)
        exec_action = None
        if not COMPUTE_M_LOCATION:
            # 如果采用动态计算m_location的方式，用户不再需要填设备宽高，按照roi来进行判断
            DefaultMixin.judge_coordinates_reasonable([click_x, click_y, click_z],
                                                      location[0] + float(device_obj.width), location[0],
                                                      location[2])
            if click_x < location[0] or (click_x - location[0]) <= X_SIDE_OFFSET_DISTANCE:
                is_left_side = True
        else:
            dpi = get_global_value('pane_dpi')
            if dpi is None or roi is None:
                raise CoordinateConvert()
            try:
                h, w, _ = get_global_value('merge_shape')
            except Exception:
                raise MergeShapeNone()

            device_scope = PaneClickTestView.get_device_scope(roi, location, dpi, h, w)
            # 点的位置在屏幕内一定为点击，屏幕外一定是按压
            exec_action = "click" if (device_scope[0] <= click_x <= device_scope[1]) and (
                    device_scope[2] <= click_y <= device_scope[3]) else "press"

            # 带传感器的柜子不允许按压
            if CORAL_TYPE in [5, 5.3, 5.4] and exec_action == "press":
                raise TcabNotAllowExecThisUnit

            # 其他柜型（5L-5.1，5se-5.2）支持按压，但需要判断按压侧边键位置的合理性
            if exec_action == "press":
                min_x = location[0] + (h - roi[3]) / dpi
                max_x = location[0] + (h - roi[1]) / dpi
                DefaultMixin.judge_coordinates_reasonable([click_x, click_y, click_z],
                                                          max_x, min_x, location[2])

                if click_x < min_x or (click_x - min_x) <= X_SIDE_OFFSET_DISTANCE:
                    is_left_side = True

        if exec_action == "click":
            exec_serial_obj, arm_num = judge_start_x(click_x, device_label)
            axis = pre_point([click_x, click_y, click_z], arm_num=arm_num)
            orders = [
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2] + 5, MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2], MOVE_SPEED),
                'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], Z_UP, MOVE_SPEED),
            ]
        else:
            # exec_action: press
            speed = MOVE_SPEED if is_normal_speed else MOVE_SPEED - 10000
            press_side_speed = PRESS_SIDE_KEY_SPEED if is_normal_speed else PRESS_SIDE_KEY_SPEED / 2
            orders = HandHandler.press_side_order([click_x, click_y, click_z], is_left=is_left_side, speed=speed,
                                                  press_side_speed=press_side_speed)
            exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(device_label, arm_com))

        return exec_serial_obj, orders, exec_action

    @staticmethod
    def get_device_scope(roi, location, dpi, h, w):
        """
        判断点击点是否在roi范围内
        click: 物理坐标值, [x, y] or [x, y, z]
        需求得最大[min_x, max_x], [mix_y, mix_y]
        """
        if CORAL_TYPE in [5.3]:
            min_x = location[0] + roi[1] / dpi
            max_x = location[0] + roi[3] / dpi
            min_y = -location[1] + (w - roi[2]) / dpi
            max_y = -location[1] + (w - roi[0]) / dpi
        else:
            min_x = location[0] + (h - roi[3]) / dpi
            max_x = location[0] + (h - roi[1]) / dpi
            min_y = -location[1] + roi[0] / dpi
            max_y = -location[1] + roi[2] / dpi

        return [min_x, max_x, min_y, max_y]

    @staticmethod
    def exec_hand_action(exec_serial_obj, orders, exec_action, ignore_reset=False, wait_time=0):
        """
        is_exec_loop: 是否正在执行测试点击多次
        """
        # 在这里计算点击或者按压的时间点 写入到redis中，用来辅助性能测试
        move_times = hand_move_times(orders, exec_serial_obj)
        if exec_action == "click":
            # 需要注意可能存在多个机械臂
            redis_client.set(CLICK_TIME, time.time() + move_times[0] + move_times[1] +
                             ACCELERATION_TIME)
            exec_serial_obj.send_out_key_order(orders[:2], others_orders=[orders[-1]], wait_time=wait_time,
                                               ignore_reset=ignore_reset)
        elif exec_action == "press":
            redis_client.set(CLICK_TIME, time.time() + move_times[0] + move_times[1] +
                             move_times[2] + ACCELERATION_TIME)
            print('按压的时间点：', redis_client.get(CLICK_TIME))
            exec_serial_obj.send_out_key_order(orders[:3], others_orders=orders[3:], wait_time=wait_time,
                                               ignore_reset=ignore_reset)
        else:
            pass
        exec_serial_obj.recv()

    @staticmethod
    def exec_action_loop(exec_serial_obj, orders, exec_action, click_count, random_dir):
        for num in range(click_count):
            if get_global_value("click_loop_stop_flag"):
                wait_position = get_wait_position(exec_serial_obj.ser.port)
                exec_serial_obj.send_single_order(wait_position)
                exec_serial_obj.recv()
                break
            ignore_reset = False if num == click_count - 1 else True
            PaneClickTestView.exec_hand_action(exec_serial_obj, orders, exec_action, ignore_reset=ignore_reset)
        set_global_value("click_loop_stop_flag", True)
        shutil.rmtree(random_dir)
        return 0


class PaneUpdateMLocation(MethodView):
    """
    更新 5系列柜子的m_location（不包含Tcab-5D）
    1. 接收从reef推送的最新的m_location数据
        如果是中心点对齐，这里实际传入的是m_location_center的值
        如果是左上角对齐，则是m_location的值
    2. 更新注册设备的m_location相关信息
    3. 更新至宿主机的/TMach_source/source/ip.py
    """

    def post(self):
        """
        {"m_location":[], "device_lable":""}
        """
        new_location_data = request.get_json()["m_location"]
        device_label = request.get_json()["device_label"]
        if get_global_value('m_location_center'):
            set_global_value('m_location_center', new_location_data)
            self.update_ip_file("m_location_center", new_location_data)
        else:
            set_global_value('m_location_original', new_location_data)
            self.update_ip_file("m_location", new_location_data)
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=device_label)
        device_obj.update_m_location()
        return jsonify(dict(error_code=0))

    @staticmethod
    def update_ip_file(location_name, new_data):
        with open(IP_FILE_PATH, "r", encoding="utf-8") as f:
            content = ""
            for line in f:
                if location_name in line and not line.startswith("#"):
                    print("被替换的数据是： ", line)
                    continue
                content += line

        new_content = content + "\n" + (location_name + "=" + str(new_data))
        with open(IP_FILE_PATH, "w", encoding='utf-8') as f2:  # 再次打开test.txt文本文件
            f2.write(new_content)  # 将替换后的内容写入到test.txt文本文件中


class PaneClickMLocation(MethodView):
    """
    点击m_location坐标，Z值需+设备厚度后再点击
    """

    def post(self):
        m_location_data_x = request.get_json()["m_location_x"]
        m_location_data_y = request.get_json()["m_location_y"]
        m_location_data_z = request.get_json()["m_location_z"]
        device_label = request.get_json()["device_label"]
        device_obj = Device(pk=device_label)
        m_location_data_z = m_location_data_z + float(device_obj.ply)
        exec_serial_obj, orders, exec_action = PaneClickTestView().get_exec_info(m_location_data_x, m_location_data_y,
                                                                                 m_location_data_z, device_label)
        PaneClickTestView().exec_hand_action(exec_serial_obj, orders, exec_action)
        return jsonify(dict(error_code=0))


class PaneClickZDown(MethodView):
    """
    测试 Z_DOWN 是否合适, Z值+设备厚度后再点击
    传入的Z值为正数，需加负号
    """

    def post(self):
        arm_num = request.get_json().get('arm_num', 0)
        recv_z_down = request.get_json()["z_down"]
        # 存放用户选择的[+x, -y]坐标，当arm_num=1时，相应的坐标也会处理成右机械臂适合的坐标值
        point = request.get_json().get('point')
        device_label = request.get_json()["device_label"]
        device_obj = Device(pk=device_label)
        click_z = -recv_z_down + float(device_obj.ply) if CORAL_TYPE != 5.3 else -recv_z_down
        exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(device_label, arm_com))
        if CORAL_TYPE == 5.3:  # 5d
            if arm_num == 1:
                exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(device_label, arm_com_1))
                point = [-(HAND_MAX_X - point[0]), point[1]]
        orders = [
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (point[0], point[1], click_z + 5, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (point[0], point[1], click_z, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (point[0], point[1], Z_UP, MOVE_SPEED),
        ]
        # 判断机械臂状态是否在执行循环
        if (not get_global_value("click_loop_stop_flag")) or (not exec_serial_obj.check_hand_status):
            return jsonify(dict(error_code=UsingHandFail.error_code,
                                description=UsingHandFail.description))
        PaneClickTestView().exec_hand_action(exec_serial_obj, orders, exec_action="click", wait_time=2)
        return jsonify(dict(error_code=0))


class PaneUpdateZDown(MethodView):

    def post(self):
        Z_DOWN = -request.get_json()["z_down"]
        PaneUpdateMLocation.update_ip_file('Z_DOWN', Z_DOWN)
        if CORAL_TYPE == 5.3:
            Z_DOWN_1 = - request.get_json()["z_down_1"]
            PaneUpdateMLocation.update_ip_file('Z_DOWN_1', Z_DOWN_1)
        device_label = request.get_json()["device_label"]
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=device_label)
        device_obj.update_m_location()
        click_xy = request.get_json()["click_xy"]
        click_xy_1 = request.get_json()["click_xy_1"] if CORAL_TYPE == 5.3 else click_xy
        with open(Z_POINT_FILE, "w+") as f:
            f.write(f"click_xy={click_xy}\n")
            f.write(f"click_xy_1={click_xy_1}\n")
        return jsonify(dict(error_code=0))


class PaneGetZDown(MethodView):
    def get(self):
        Z_DOWN, Z_DOWN_1 = read_z_down_from_file()
        data = {"z_down": -Z_DOWN}
        if CORAL_TYPE == 5.3:
            data.update({'z_down_1': (-Z_DOWN if not Z_DOWN_1 else -Z_DOWN_1)})
        click_xy = []
        if not os.path.exists(Z_POINT_FILE):
            if CORAL_TYPE == 5.3:  # 5d
                click_xy = [100, -100]
                data.update({'click_xy_1': [200, -100]})
            elif CORAL_TYPE == 5.2:  # 5se
                click_xy = [90, -120]
            elif CORAL_TYPE in [5, 5.4]:  # 5升级版加了延长杆
                click_xy = [85, -170]
            else:  # 5l
                click_xy = [170, -170]
        else:
            with open(Z_POINT_FILE, 'rt') as f:
                for line in f.readlines():
                    key, value = line.strip('\n').split('=')
                    if key == 'click_xy':
                        click_xy = eval(value)
                    if key == 'click_xy_1':
                        click_xy_1 = eval(value)
                if CORAL_TYPE == 5.3:
                    data.update({'click_xy_1': click_xy_1})
        data.update({'click_xy': click_xy})
        return jsonify(dict(error_code=0, data=data))


# 待命位置
class PaneWaitPosition(MethodView):

    # 获取待命位置
    def get(self):
        data = {"arm_wait_point": get_global_value("arm_wait_point")}
        if CORAL_TYPE == 5.3:
            data.update({"arm_wait_point_1": get_global_value("arm_wait_point_1")})
        return jsonify(dict(error_code=0, data=data))

    # 测试待命位置
    def post(self):
        device_label = request.get_json()["device_label"]
        arm_num = request.get_json().get('arm_num', 0)
        wait_point = request.get_json().get('arm_wait_point', 0)
        exec_serial_obj, now_wait_position, orders = None, None, []
        if CORAL_TYPE == 5.3 and arm_num == 1:  # 5d
            exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(device_label, arm_com_1))
            now_wait_position = get_global_value("arm_wait_point_1")
            wait_point[0] = -wait_point[0]
            move_list = [[wait_point[0], wait_point[1], wait_point[2], 8000],
                         [-now_wait_position[0], now_wait_position[1], now_wait_position[2], 8000]]
        else:
            exec_serial_obj = hand_serial_obj_dict.get(get_hand_serial_key(device_label, arm_com))
            now_wait_position = get_global_value("arm_wait_point")
            move_list = [[wait_point[0], wait_point[1], wait_point[2], 8000],
                         [now_wait_position[0], now_wait_position[1], now_wait_position[2], 8000]]
        for move in move_list:
            orders.append('G01 X%0.1fY%0.1fZ%0.1fF%d \r\n' % (move[0], move[1], move[2], move[3]))
        if (not get_global_value("click_loop_stop_flag")) or (not exec_serial_obj.check_hand_status):
            return jsonify(dict(error_code=UsingHandFail.error_code,
                                description=UsingHandFail.description))
        exec_serial_obj.send_out_key_order(orders[:1], others_orders=orders[1:], wait_time=2, ignore_reset=True)
        exec_serial_obj.recv()
        return jsonify(dict(error_code=0))

    # 更新待命位置
    def put(self):
        arm_wait_point = request.get_json()["arm_wait_point"]
        with open(WAIT_POSITION_FILE, "w+") as f:
            f.write(f"arm_wait_point={arm_wait_point}\n")
            if CORAL_TYPE == 5.3:
                arm_wait_point_1 = request.get_json()["arm_wait_point_1"]
                f.write(f"arm_wait_point_1={arm_wait_point_1}\n")
        read_wait_position()
        for obj_key in hand_serial_obj_dict.keys():
            if arm_com in obj_key and not obj_key[-1].isdigit():
                hand_serial_obj_dict[obj_key].send_single_order(get_global_value("arm_wait_position"))
                hand_serial_obj_dict[obj_key].recv()
            if arm_com_1 in obj_key and obj_key[-1].isdigit():
                hand_serial_obj_dict[obj_key].send_single_order(get_global_value("arm_wait_position_1"))
                hand_serial_obj_dict[obj_key].recv()
        return jsonify(dict(error_code=0))


# 获取坐标换算时的点击坐标
class PaneGetCoordinateView(MethodView):

    def get(self):
        start_point, end_point = [], []
        if not os.path.exists(COORDINATE_POINT_FILE):
            # 使用默认值
            if CORAL_TYPE == 5.3:
                start_point, end_point = [100, -100], [200, -100]
            elif CORAL_TYPE == 5:
                start_point, end_point = [55, -250], [90, -250]
            elif CORAL_TYPE == 5.4:
                start_point, end_point = [35, -210], [85, -210]
            elif CORAL_TYPE == 5.1:
                start_point, end_point = [110, -220], [160, -220]
            else:
                start_point, end_point = [50, -120], [100, -120]
        else:
            with open(COORDINATE_POINT_FILE, 'rt') as f:
                for line in f.readlines():
                    key, value = line.strip('\n').split('=')
                    if key == 'start_point':
                        start_point = eval(value)
                    if key == 'end_point':
                        end_point = eval(value)
        return jsonify(dict(error_code=0, data={"start_point": start_point, "end_point": end_point}))


# 点击坐标换算的物理坐标点
class PaneClickCoordinateView(MethodView):
    """
    点一个物理坐标点
    device_label, x, y
    """

    def post(self):
        device_label = request.get_json()["device_label"]
        point = request.get_json()["point"]
        judge_ret = DefaultMixin.judge_coordinate_in_arm(point)
        if not judge_ret:
            return jsonify(dict(error_code=CrossMax.error_code,
                                description=CrossMax.description))
        # 获取机械臂执行对象
        exec_serial_obj, arm_num = judge_start_x(point[0], device_label)
        axis = pre_point([point[0], abs(point[1])], arm_num=arm_num)

        # 判断机械臂状态是否在执行循环
        if (not get_global_value("click_loop_stop_flag")) or (not exec_serial_obj.check_hand_status):
            return jsonify(dict(error_code=UsingHandFail.error_code,
                                description=UsingHandFail.description))

        # 执行点击
        orders = [
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2] + 5, MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], axis[2], MOVE_SPEED),
            'G01 X%0.1fY%0.1fZ%dF%d \r\n' % (axis[0], axis[1], Z_UP, MOVE_SPEED),
        ]
        exec_serial_obj.send_list_order(orders)
        exec_serial_obj.recv()
        return jsonify(dict(error_code=0))


# 5D等自动建立坐标系统
class PaneCoordinateView(MethodView):
    # 确定俩件事情，一个是比例，也就是一个像素等于实际多少毫米。另一个是图片坐标系统下的原点实际的坐标值。
    def post(self):
        positions = [[request.get_json()["start_point"], request.get_json()["end_point"]]]
        dpi = 0
        m_location = [0, 0, 0]
        # 让机械臂点击一个点，在屏幕上留下了一个记号A，再让机械臂点击另一个点，在屏幕上留下了记号B
        # 计算A、B俩点的像素距离，和实际距离的比，就得到了比例。根据比例，计算原点的坐标值。
        # 找到主机械臂，让主机械臂移动即可
        # 双指的范围更大，点击的时候尽量在中间点击即可
        all_dpi = []
        all_m_location = []
        for pos_a, pos_b in positions:
            for obj_key in hand_serial_obj_dict.keys():
                # 单指机械臂直接进来
                if (arm_com in obj_key and not obj_key[-1].isdigit()) or CORAL_TYPE != 5.3:
                    hand_obj = hand_serial_obj_dict[obj_key]
                    # 双指的范围更大，点击的时候尽量在中间点击即可
                    for click_pos in [pos_a, pos_b]:
                        self.click(*click_pos, hand_obj)
                    request_data = request.get_json() or request.args
                    if request_data is not None:
                        device_label = request_data.get('device_label')
                        device_obj = Device(pk=device_label)
                    elif len(Device.all()) == 1:
                        device_obj = Device.first()
                    else:
                        return jsonify(dict(error_code=1, description='坐标换算失败！无法获取图片！'))

                    # 拍照
                    filename = 'coordinate.png'
                    ret_code = device_obj.get_snapshot(filename, max_retry_time=1, original=True)
                    if ret_code == 0:
                        print('dpi计算拍到照片了')
                        dpi, m_location = self.get_scale(filename, pos_a, pos_b)
                        if dpi is None:
                            raise CoordinateConvertFail()
                        all_dpi.append(dpi)
                        all_m_location.append(m_location)
                    break

        all_dpi = np.array(all_dpi)
        all_m_location = np.array(all_m_location)
        result_dpi = all_dpi.mean(axis=0)
        result_m_location = all_m_location.mean(axis=0)
        print(result_dpi)
        print(result_m_location)
        # 写入到文件中，方便初始化的时候获取，这里也是这俩个值更新的唯一地方
        z_down = get_global_value('Z_DOWN')
        set_global_value('m_location', [result_m_location[0], result_m_location[1], z_down])
        set_global_value('pane_dpi', result_dpi)
        merge_shape = get_global_value('merge_shape')
        with open(COORDINATE_CONFIG_FILE, 'wt') as f:
            f.writelines(f'm_location=[{result_m_location[0]},{result_m_location[1]}]\n')
            f.writelines(f'pane_dpi={result_dpi}\n')
            f.writelines(f'merge_shape={merge_shape}\n')

        # 坐标换算完成
        with open(COORDINATE_POINT_FILE, "w+") as f:
            f.write(f"start_point={positions[0][0]}\n")
            f.write(f"end_point={positions[0][1]}\n")

        reference_dpi = REFERENCE_VALUE["reference_" + str(int(CORAL_TYPE * 10))]["dpi"]
        reference_location = REFERENCE_VALUE["reference_" + str(int(CORAL_TYPE * 10))]["m_location"]
        return jsonify(dict(error_code=0,
                            description=f"坐标换算完成。dpi为【{dpi}】,参考值【{reference_dpi}】；mlocation为【{m_location[0]},{m_location[1]}】，参考值为【{reference_location[0]}, {reference_location[1]}】"))

    # 传入x,y俩个值即可
    @staticmethod
    def get_click_orders(pos_x, pos_y, hand_obj):
        z_down = get_global_value('Z_DOWN')
        z_up = round(z_down + 10, 2)
        wait_position = get_wait_position(hand_obj.ser.port)
        return [f"G01 X{pos_x}Y{pos_y}Z{z_up}F15000\r\n",
                f"G01 X{pos_x}Y{pos_y}Z{z_down}F15000\r\n",
                f"G01 X{pos_x}Y{pos_y}Z{z_up}F15000\r\n",
                wait_position]

    def click(self, pos_x, pos_y, hand_obj):
        click_orders = self.get_click_orders(pos_x, pos_y, hand_obj)
        for order in click_orders:
            hand_obj.send_single_order(order)
        hand_obj.recv(buffer_size=64)

    @staticmethod
    def get_scale(filename, pos_a, pos_b):
        img = cv2.imread(filename)
        h, w, _ = img.shape
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 机械臂点下的点需要是红色的
        lower_red = np.array([0, 43, 46])
        upper_red = np.array([10, 255, 255])
        mask_1 = cv2.inRange(hsv, lower_red, upper_red)

        lower_red = np.array([156, 43, 46])
        upper_red = np.array([180, 255, 255])
        mask_2 = cv2.inRange(hsv, lower_red, upper_red)

        mask = mask_1 + mask_2

        # kernel = np.uint8(np.ones((3, 3)))
        # mask = cv2.dilate(mask, kernel, iterations=2)

        # 获取符合条件的轮廓
        _, contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        target_contours = []
        # 查找符合条件的轮廓
        for contour_index, contour_points in enumerate(contours):
            # 遍历组成轮廓的每个坐标点
            m = cv2.moments(contour_points)
            # m00代表面积
            if 50 < m['m00']:
                # 获取对象的质心
                cx = round(m['m10'] / m['m00'], 2)
                cy = round(m['m01'] / m['m00'], 2)
                if w * 0.2 < cx < w * 0.9:
                    bx, by, bw, bh = cv2.boundingRect(contour_points)
                    if 0.7 < bw / bh < 1.3:
                        target_contours.append(np.array([[cx, cy]]))

        def find_tow_related_point(all_contours):
            for i in range(len(all_contours)):
                for j in range(i + 1, len(all_contours)):
                    # x坐标基本一样
                    if abs(all_contours[i][0][0] - all_contours[j][0][0]) < 7 and abs(
                            all_contours[i][0][1] - all_contours[j][0][1]) > 100:
                        return [all_contours[i], all_contours[j]]

        print(target_contours)
        target_contours = find_tow_related_point(target_contours)
        if target_contours and len(target_contours) == 2:
            print('相机的倾斜程度：', target_contours)
            # A、B俩点的x像素坐标默认是相等的。根据这个默认条件执行以下的逻辑。实际上得出来的A、B俩点的x像素坐标不一样，原因是相机是歪的。
            dis = abs(target_contours[0][0][1] - target_contours[1][0][1])
            # 实际上就是dpi 代表1毫米多少个像素点
            dpi = round(dis / abs(pos_a[0] - pos_b[0]), 3)
            print(f'dpi:{dpi}', '&' * 10)
            # 计算图片的右上角（5D）或者左下角（5系列的其他相机）对应的坐标点，也就是得出来m_location
            if CORAL_TYPE == 5.3:
                cal_point = target_contours[0] if target_contours[0][0][1] < target_contours[1][0][1] else \
                    target_contours[1]
                m_x = round(pos_a[0] - cal_point[0][1] / dpi, 2)
                m_y = round(pos_a[1] + (w - cal_point[0][0]) / dpi, 2)
            else:
                cal_point = target_contours[1] if target_contours[0][0][1] < target_contours[1][0][1] else \
                    target_contours[0]
                m_x = round(pos_a[0] - (h - cal_point[0][1]) / dpi, 2)
                # 计算左上角的m_location
                m_y = round(pos_a[1] + cal_point[0][0] / dpi, 2)
                # 计算左下角的m_location
                # m_y = round(pos_a[1] - (w - cal_point[0][0]) / dpi, 2)

            return dpi, [m_x, m_y]

        # 画出轮廓，方便测试
        img = cv2.drawContours(img, contours, -1, (0, 255, 0), 3)
        cv2.imwrite('result.png', img)
        # 没有找到的话抛出异常
        return None, None


# 重置5D等拼接图像的参数
class PaneMergePicView(MethodView):
    # 删除文件，重置全局变量
    def post(self):
        try:
            if os.path.exists(MERGE_IMAGE_H):
                os.remove(MERGE_IMAGE_H)
            set_global_value(MERGE_IMAGE_H, None)
            set_global_value('merge_shape', None)
            return jsonify(dict(error_code=0))
        except Exception as e:
            print(e)
            return jsonify(dict(error_code=1, description='重置失败！'))


# 调试距离
class PaneLocateDeviceView(MethodView):
    # 根据z的值，移动被测试设备
    def post(self):
        for hand_key in hand_serial_obj_dict.keys():
            # 找到主机械臂，让主机械臂移动即可
            if arm_com in hand_key and not hand_key[-1].isdigit():
                hand_obj = hand_serial_obj_dict[hand_key]
                pos_x = 100
                pos_y = -100
                z_down = get_global_value('Z_DOWN')
                click_orders = [f"G01 X{pos_x}Y{pos_y}Z{z_down + 10}F15000\r\n",
                                f"G01 X{pos_x}Y{pos_y}Z{z_down}F15000\r\n"]
                for order in click_orders:
                    hand_obj.send_single_order(order)
                hand_obj.recv(buffer_size=32)
                # 等待一段时间，方便用户调试
                time.sleep(5)
                wait_postion = get_wait_position(hand_obj.ser.port)
                click_orders = [f"G01 X{pos_x}Y{pos_y}Z{z_down + 10}F15000\r\n", wait_postion]
                for order in click_orders:
                    hand_obj.send_single_order(order)
                hand_obj.recv(buffer_size=32)
                break
        return jsonify(dict(error_code=0))


# 录制视频
class PaneVideoView(MethodView):
    def post(self):
        request_data = request.get_json() or request.args
        device_label = request_data.get("device_label")
        record_time = request_data.get('record_time')
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=device_label)
        device_obj.get_snapshot(image_path='', max_retry_time=1,
                                record_video=True,
                                record_time=int(record_time),
                                timeout=10 * 60)
        return jsonify(dict(error_code=0))


# 泰尔五星认证 中心五点打点
class ClickCenterPointFive(MethodView):

    def get(self):
        # 获取机械臂对象
        hand_obj = None
        for obj_key in hand_serial_obj_dict.keys():
            # 单指机械臂直接进来
            if (arm_com in obj_key and not obj_key[-1].isdigit()) or CORAL_TYPE != 5.3:
                hand_obj = hand_serial_obj_dict[obj_key]

        request_data = request.get_json() or request.args
        device_label = request_data["device_label"]
        device_obj = Device(pk=device_label)

        filename = 'point_5_1.png'
        ret_code = device_obj.get_snapshot(filename, max_retry_time=1, original=False)
        if ret_code == 0:
            print('point 5 1 拍到照片了')
            target_points = self.get_black_point(filename)
            print(target_points)
            for point in target_points:
                # 随机误差
                # random_point = [point[0] + random.randint(1, 5), point[1] + random.randint(1, 5)]
                self.click(device_obj, hand_obj, *point)
                time.sleep(1)

        filename = 'point_5_2.png'
        ret_code = device_obj.get_snapshot(filename, max_retry_time=1, original=False)
        if ret_code == 0:
            print('point 5 2 拍到照片了')
            red_points = self.get_red_point(filename)
            print(red_points)

        # 计算俩点之间的距离
        dpi = get_global_value('pane_dpi')
        all_dis = []
        for i in range(len(red_points)):
            dis = math.sqrt(math.pow(red_points[i][0] - target_points[i][0], 2) +
                            math.pow(red_points[i][1] - target_points[i][1], 2))
            all_dis.append(round(dis / dpi, 2))
            print(round(dis / dpi, 2))

        return jsonify(dict(error_code=0, data=all_dis))

    @staticmethod
    def get_black_point(filename):
        img = cv2.imread(filename)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
        # cv2.imwrite('1.png', binary)

        _, contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, contours, -1, (0, 255, 0), 3)
        # cv2.imwrite('result.png', img)

        target_points = []
        # 查找符合条件的轮廓
        for contour_index, contour_points in enumerate(contours):
            # 遍历组成轮廓的每个坐标点
            m = cv2.moments(contour_points)
            # m00代表面积
            if m['m00'] < 1000:
                # 获取对象的质心
                cx = round(m['m10'] / m['m00'], 2)
                cy = round(m['m01'] / m['m00'], 2)
                # print(cx, cy)
                target_points.append([cx, cy])

        return target_points

    @staticmethod
    def get_red_pic(img, is_dilate=True):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 机械臂点下的点需要是红色的
        lower_red = np.array([0, 43, 46])
        upper_red = np.array([10, 255, 255])
        mask_1 = cv2.inRange(hsv, lower_red, upper_red)

        lower_red = np.array([156, 43, 46])
        upper_red = np.array([180, 255, 255])
        mask_2 = cv2.inRange(hsv, lower_red, upper_red)

        mask = mask_1 + mask_2

        if is_dilate:
            kernel = np.uint8(np.ones((3, 3)))
            mask = cv2.dilate(mask, kernel, iterations=2)
        # cv2.imwrite('mask.png', mask)

        return mask

    @staticmethod
    def get_red_point(filename):
        img = cv2.imread(filename)
        mask = ClickCenterPointFive.get_red_pic(img)

        # 获取符合条件的轮廓
        _, contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        # cv2.drawContours(img, contours, -1, (0, 255, 0), 3)

        target_points = []
        for contour_index, contour_points in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour_points)
            # 必须是一个圆，判断外接矩形即可
            if 0.8 < w / h < 1.1:
                # cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                # 遍历组成轮廓的每个坐标点
                m = cv2.moments(contour_points)
                if m['m00'] > 150:
                    # 获取对象的质心
                    cx = round(m['m10'] / m['m00'], 2)
                    cy = round(m['m01'] / m['m00'], 2)
                    target_points.append([cx, cy])

        # cv2.imwrite('result.png', img)
        return target_points

    @staticmethod
    def get_lines(filename):
        img = cv2.imread(filename)
        mask = ClickCenterPointFive.get_red_pic(img)

        # 获取符合条件的轮廓
        _, contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        # cv2.drawContours(img, contours, -1, (0, 255, 0), 3)

        target_points = []
        for contour_index, contour_points in enumerate(contours):
            rect = cv2.minAreaRect(contour_points)
            # 这里可能损失精度
            box = np.int0(cv2.boxPoints(rect))
            # 线的长度至少得是120像素
            if rect[1][0] > 120 or rect[1][1] > 120:
                # cv2.drawContours(img, [box], -1, (0, 255, 0), 1)
                # 是一条从上到下的直线
                if rect[1][1] > rect[1][0] and abs(rect[2]) < 2:
                    left_points = [point for point in box if point[1] < rect[0][1]]
                elif rect[1][0] > rect[1][1] and abs(rect[2]) > 87:
                    left_points = [point for point in box if point[1] < rect[0][1]]
                else:
                    left_points = [point for point in box if point[0] < rect[0][0]]

                if len(left_points) == 2:
                    target_points.append((left_points[0] + left_points[1]) / 2)

                # 调试的时候打开，很方便能看出问题
                # img = cv2.putText(img.copy(), f'{target_points[-1]}',
                #                   (int(target_points[-1][0]), int(target_points[-1][1])),
                #                   cv2.FONT_HERSHEY_COMPLEX, 1.0, (0, 0, 255), 1)

        # cv2.imwrite('result.png', img)
        return target_points

    @staticmethod
    def sub_point(pre_points, cur_points):
        result_point = []
        for cur_p in cur_points:
            is_new = True
            for pre_p in pre_points:
                dis = math.sqrt(math.pow(cur_p[0] - pre_p[0], 2) + math.pow(cur_p[1] - pre_p[1], 2))
                # print(dis, '&' * 10)
                if dis < 3:
                    is_new = False
                    break
            if is_new:
                result_point.append(cur_p)
        return result_point

    def get_contours(self, filename, result_filename):
        img = cv2.imread(filename)
        img = cv2.GaussianBlur(img, (3, 3), 0)
        src = self.get_red_pic(img, False)

        # cv2.imwrite('blur.png', src)

        # 获取符合条件的轮廓
        _, contours, hierarchy = cv2.findContours(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        target_points = []
        for contour_index, contour_points in enumerate(contours):
            m = cv2.moments(contour_points)
            if m['m00'] > 50:
                target_points.append(contour_points)

        for contour_index, contour in enumerate(target_points):
            img = cv2.putText(img.copy(), f'{contour_index + 1}',
                              (int(contour[0][0][0]), int(contour[0][0][1])),
                              cv2.FONT_HERSHEY_COMPLEX, 1.0, (255, 0, 0), 2)

        # cv2.drawContours(img, contours, -1, (0, 255, 0), 1)
        cv2.imwrite(result_filename, img)

        return len(target_points) - 1

    def click(self, device_obj, hand_obj, point_x, point_y):
        pos_x, pos_y, pos_z = device_obj.get_click_position(point_x, point_y, absolute=True)
        print(pos_x, pos_y, pos_z, '*' * 10)
        click_orders = self.get_click_orders(pos_x, -pos_y, pos_z, hand_obj)
        for order in click_orders:
            hand_obj.send_single_order(order)
        hand_obj.recv(buffer_size=64)

    @staticmethod
    def get_click_orders(pos_x, pos_y, pos_z, hand_obj):
        wait_position = get_wait_position(hand_obj.ser.port)
        z_up = pos_z + 5
        return [f"G01 X{pos_x}Y{pos_y}Z{z_up}F15000\r\n",
                f"G01 X{pos_x}Y{pos_y}Z{pos_z}F15000\r\n",
                f"G01 X{pos_x}Y{pos_y}Z{z_up}F15000\r\n",
                wait_position]


class PaneMkDir(MethodView):

    def post(self):
        request_data = request.get_json() or request.args
        dir_path = request_data.get('dir_path')
        if not dir_path:
            return jsonify(dict(error_message='dir_path is necessary')), 500

        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        return jsonify(dict(error_code=0, data={'dir_path': f'mk dir {dir_path} success'}))
