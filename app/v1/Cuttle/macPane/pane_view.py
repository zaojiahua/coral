import logging
import os.path
import platform
import random
import shutil
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
from PIL import Image
from flask import request, jsonify, Response
from flask.views import MethodView
from serial import SerialException

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import SUCCESS_PIC_NAME, FAIL_PIC_NAME, LEAVE_PIC_NAME, PANE_LOG_NAME, DEVICE_BRIGHTNESS, \
    arm_com_1, Z_DOWN, CORAL_TYPE, arm_com, arm_com_1_sensor, PROJECT_SIBLING_DIR, BASE_DIR
from app.execption.outer.error_code.camera import PerformancePicNotFound
from app.execption.outer.error_code.hands import UsingHandFail, CoordinatesNotReasonable
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.hand_serial import controlUsbPower
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import camera_start
from app.v1.Cuttle.basic.operator.hand_operate import hand_init, rotate_hand_init, HandHandler, judge_start_x, \
    pre_point, sensor_init
from app.v1.Cuttle.basic.calculater_mixin.default_calculate import DefaultMixin
from app.v1.Cuttle.basic.operator.handler import Dummy_model
from app.v1.Cuttle.basic.setting import hand_serial_obj_dict, rotate_hand_serial_obj_dict, get_global_value, \
    MOVE_SPEED, X_SIDE_OFFSET_DISTANCE, PRESS_SIDE_KEY_SPEED, arm_wait_position, set_global_value, \
    COORDINATE_CONFIG_FILE, MERGE_IMAGE_H, Z_UP
from app.v1.Cuttle.macPane.schema import PaneSchema, OriginalPicSchema, CoordinateSchema, ClickTestSchema
from app.v1.Cuttle.network.network_api import unbind_spec_ip
from app.v1.device_common.device_model import Device
from app.v1.tboard.views.get_dut_progress import get_dut_progress_inner
from app.v1.tboard.views.stop_specific_device import stop_specific_device_inner
from redis_init import redis_client

import copy

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
        # 推送结束图片
        if device_object.ip_address != "0.0.0.0":
            pic_push(device_object, pic_name=LEAVE_PIC_NAME)
        if device_object.has_rotate_arm:
            # todo  clear used list when only one arm for one server
            self._reset_arm(device_object)
        if device_object.has_arm:
            try:
                hand_serial_obj = hand_serial_obj_dict[device_object.pk]
                hand_serial_obj.close()
            except KeyError:
                # 多见与机柜型号填写有误时
                pass
        if device_object.has_camera:
            redis_client.set("g_bExit", "1")
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
        # 传感器
        elif port.startswith('/dev/arm_sensor_'):
            com_index = arm_com_1_sensor.split('_')[-1]
            function, attribute = (sensor_init, "has_sensor_" + com_index)
        # or是针对win的条件，方便测试
        elif port.startswith('/dev/arm_sensor') or port == 'COM27':
            function, attribute = (sensor_init, 'has_sensor')
        elif port.startswith('/dev/arm_'):
            com_index = arm_com_1.split('_')[-1]
            function, attribute = (hand_init, "has_arm_" + com_index)
        else:
            function, attribute = (hand_init, "has_arm")
            controlUsbPower(status='init')
        setattr(device_object, attribute, True)
        return function, device_object


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
        exec_serial_obj, orders, exec_action = self.get_exec_info(click_x, click_y, click_z, device_label)

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
                raise UsingHandFail

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
    def get_exec_info(click_x, click_y, click_z, device_label):
        """
        return: serial_obj, orders
        """
        is_left_side = False
        if CORAL_TYPE == 5.3:
            exec_action = "click"
        else:
            # 判断是否是按压侧边键
            location = get_global_value("m_location")
            try:
                device_obj = Device(pk=device_label)
                DefaultMixin.judge_coordinates_reasonable([click_x, click_y, click_z],
                                                          location[0] + float(device_obj.width), location[0],
                                                          location[2])
                if click_x < location[0] or (click_x - location[0]) <= X_SIDE_OFFSET_DISTANCE:
                    is_left_side = True
                exec_action = "press"
            except CoordinatesNotReasonable:
                exec_action = "click"

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
            speed = MOVE_SPEED - 10000
            press_side_speed = PRESS_SIDE_KEY_SPEED / 2
            orders = HandHandler.press_side_order([click_x, click_y, click_z], is_left=is_left_side, speed=speed,
                                                  press_side_speed=press_side_speed)
            exec_serial_obj = hand_serial_obj_dict.get(device_label)

        return exec_serial_obj, orders, exec_action

    @staticmethod
    def exec_hand_action(exec_serial_obj, orders, exec_action, ignore_reset=False):
        """
        is_exec_loop: 是否正在执行测试点击多次
        """
        if exec_action == "click":
            exec_serial_obj.send_list_order(orders, ignore_reset=ignore_reset)
        elif exec_action == "press":
            exec_serial_obj.send_out_key_order(orders[:3], others_orders=orders[3:], wait_time=0,
                                               ignore_reset=ignore_reset)
        else:
            pass
        exec_serial_obj.recv()

    @staticmethod
    def exec_action_loop(exec_serial_obj, orders, exec_action, click_count, random_dir):
        for num in range(click_count):
            if get_global_value("click_loop_stop_flag"):
                exec_serial_obj.send_single_order(arm_wait_position)
                exec_serial_obj.recv()
                break
            ignore_reset = False if num == click_count - 1 else True
            PaneClickTestView.exec_hand_action(exec_serial_obj, orders, exec_action, ignore_reset=ignore_reset)
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
        if platform.system() == 'Linux':
            file = '/app/source/ip.py'
        else:
            file = os.path.join(BASE_DIR, "app", "config", "ip.py")
        old_data = None
        with open(file, "r", encoding="utf-8") as f:
            content = ""
            for line in f:
                if location_name in line and not line.startswith("#"):
                    old_data = line.split("=")[1].split("]")[0].strip(" ")
                    print("老数据：", old_data)
                content += line

        if not old_data:
            raise Exception("ip.py 配置文件有问题，请检查!")

        new_content = content.replace(old_data, str(new_data).split("]")[0])

        with open(file, "w", encoding='utf-8') as f2:  # 再次打开test.txt文本文件
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


# 5D等自动建立坐标系统
class PaneCoordinateView(MethodView):
    # 确定俩件事情，一个是比例，也就是一个像素等于实际多少毫米。另一个是图片坐标系统下的原点实际的坐标值。
    def post(self):
        dpi = 0
        m_location = [0, 0, 0]
        # 让机械臂点击一个点，在屏幕上留下了一个记号A，再让机械臂点击另一个点，在屏幕上留下了记号B
        # 计算A、B俩点的像素距离，和实际距离的比，就得到了比例。根据比例，计算原点的坐标值。
        # 找到主机械臂，让主机械臂移动即可
        for obj_key in hand_serial_obj_dict.keys():
            if arm_com in obj_key and not obj_key[-1].isdigit():
                hand_obj = hand_serial_obj_dict[obj_key]
                pos_a = [100, -100]
                pos_b = [200, -100]
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
                    print('拍到照片了')
                    dpi, m_location = self.get_scale(filename, pos_a, pos_b)
                    # if dpi is not None:
                    #     # 测试计算的是否正确 点击左上角
                    #     points = AutoPaneBorderView.get_suitable_area(cv2.imread(filename), 60)
                    #     if points is not None:
                    #         click_x, click_y, _ = device_obj.get_click_position(*points[1], test=True)
                    #         self.click(click_x, -click_y, hand_obj)
                break

        return jsonify(dict(error_code=0, data={'dpi': dpi, 'm_location': m_location}))

    # 传入x,y俩个值即可
    @staticmethod
    def get_click_orders(pos_x, pos_y):
        z_down = get_global_value('Z_DOWN')
        return [f"G01 X{pos_x}Y{pos_y}Z{z_down + 10}F15000\r\n",
                f"G01 X{pos_x}Y{pos_y}Z{z_down}F15000\r\n",
                f"G01 X{pos_x}Y{pos_y}Z{z_down + 10}F15000\r\n",
                arm_wait_position]

    def click(self, pos_x, pos_y, hand_obj):
        click_orders = self.get_click_orders(pos_x, pos_y)
        for order in click_orders:
            hand_obj.send_single_order(order)
        hand_obj.recv(buffer_size=64)

    @staticmethod
    def get_scale(filename, pos_a, pos_b):
        img = cv2.imread(filename)
        _, w, _ = img.shape
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 机械臂点下的点需要是红色的
        lower_red = np.array([0, 43, 46])
        upper_red = np.array([10, 255, 255])
        mask_1 = cv2.inRange(hsv, lower_red, upper_red)

        lower_red = np.array([156, 43, 46])
        upper_red = np.array([180, 255, 255])
        mask_2 = cv2.inRange(hsv, lower_red, upper_red)

        mask = mask_1 + mask_2

        kernel = np.uint8(np.ones((3, 3)))
        mask = cv2.dilate(mask, kernel, iterations=2)

        # 获取符合条件的轮廓
        _, contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        target_contours = []
        # 查找符合条件的轮廓
        for contour_index, contour_points in enumerate(contours):
            # 遍历组成轮廓的每个坐标点
            m = cv2.moments(contour_points)
            # m00代表面积
            if m['m00'] > 50:
                # 获取对象的质心
                cx = int(m['m10'] / m['m00'])
                cy = int(m['m01'] / m['m00'])
                if w * 0.3 < cx < w * 0.6:
                    bx, by, bw, bh = cv2.boundingRect(contour_points)
                    if 0.9 < bw / bh < 1.1:
                        target_contours.append(np.array([[int(cx), int(cy)]]))

        if len(target_contours) == 2:
            # A、B俩点的x像素坐标默认是相等的。根据这个默认条件执行以下的逻辑。实际上得出来的A、B俩点的x像素坐标不一样，原因是相机是歪的。
            dis = abs(target_contours[0][0][1] - target_contours[1][0][1])
            # 实际上就是dpi 代表1毫米多少个像素点
            dpi = dis / abs(pos_a[0] - pos_b[0])
            print(f'dpi:{dpi}', '&' * 10)
            # 计算图片的右上角对应的坐标点，也就是得出来m_location
            cal_point = target_contours[0] if target_contours[0][0][1] < target_contours[1][0][1] else target_contours[
                1]
            m_x = pos_a[0] - cal_point[0][1] / dpi
            m_y = pos_a[1] + (w - cal_point[0][0]) / dpi

            # 写入到文件中，方便初始化的时候获取，这里也是这俩个值更新的唯一地方
            set_global_value('m_location', [m_x, m_y, Z_DOWN])
            set_global_value('pane_dpi', dpi)
            with open(COORDINATE_CONFIG_FILE, 'wt') as f:
                f.writelines(f'm_location=[{m_x},{m_y}]\n')
                f.writelines(f'pane_dpi={dpi}\n')

            # 画出轮廓，方便测试
            # img = cv2.drawContours(img, target_contours, -1, (0, 255, 0), 30)

            return dpi, [m_x, m_y, Z_DOWN]


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
                click_orders = [f"G01 X{pos_x}Y{pos_y}Z{z_down + 10}F15000\r\n", arm_wait_position]
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
