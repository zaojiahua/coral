import logging
import os.path
import random
import shutil
import subprocess
import sys
import traceback

import cv2
import numpy as np
from PIL import Image
from flask import request, jsonify, Response
from flask.views import MethodView
from serial import SerialException

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import SUCCESS_PIC_NAME, FAIL_PIC_NAME, LEAVE_PIC_NAME, PANE_LOG_NAME, DEVICE_BRIGHTNESS
from app.execption.outer.error_code.camera import ArmReInit, NoCamera, PerformancePicNotFound
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import camera_start
from app.v1.Cuttle.basic.operator.hand_operate import hand_init, rotate_hand_init
from app.v1.Cuttle.basic.operator.handler import Dummy_model
from app.v1.Cuttle.basic.setting import hand_serial_obj_dict, rotate_hand_serial_obj_dict, m_location, get_global_value, \
    MOVE_SPEED
from app.v1.Cuttle.macPane.schema import PaneSchema, OriginalPicSchema, CoordinateSchema, ClickTestSchema
from app.v1.Cuttle.network.network_api import unbind_spec_ip
from app.v1.device_common.device_model import Device
from app.v1.tboard.views.get_dut_progress import get_dut_progress_inner
from app.v1.tboard.views.stop_specific_device import stop_specific_device_inner
from redis_init import redis_client

from concurrent.futures._base import TimeoutError
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
    def hardware_init(port, device_label, executer, rotate=False):
        try:
            device_object = Device(pk=device_label)
            if rotate is True:
                function, attribute = (rotate_hand_init, "has_rotate_arm")
            elif port.split("/")[-1].isdigit():
                function, attribute = (camera_start, "has_camera")
            else:
                function, attribute = (hand_init, "has_arm")
            setattr(device_object, attribute, True)
            future = executer.submit(function, port, device_object, init=True)
            exception = future.exception(timeout=2)
            print(exception, '*' * 10)
            if "PermissionError" in str(exception):
                traceback.print_exc()
                raise ArmReInit
            elif "FileNotFoundError" in str(exception):
                return 0
            elif "tolist" in str(exception):
                raise NoCamera
        except TimeoutError:
            print('TimeoutError')
            return 0


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
        kernel = np.uint8(np.ones((3, 3)))
        src = cv2.erode(src, kernel, iterations=2)
        src = cv2.dilate(src, kernel, iterations=2)
        gray = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY)
        ret, binary = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
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
        except IndexError:
            return jsonify(
                {"status": "can not find suitable area, please make sure phone is showing a light page"}), 400
        point.sort(key=lambda x: x[0] + x[1])
        return jsonify({"upper_left_x": int(point[0][0]),
                        "upper_left_y": int(point[0][1]),
                        "under_right_x": int(point[3][0]),
                        "under_right_y": int(point[3][1]),
                        }), 200


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

        click_x, click_y, click_z = device_obj.get_click_position(int(request_data.get('x')),
                                                                  int(request_data.get('y')),
                                                                  int(request_data.get('z')),
                                                                  [int(request_data.get('inside_upper_left_x')),
                                                                   int(request_data.get('inside_upper_left_y')),
                                                                   int(request_data.get('inside_under_right_x')),
                                                                   int(request_data.get('inside_under_right_y'))])
        self.click(device_label, click_x, click_y, click_z)

        shutil.rmtree(random_dir)
        return jsonify(dict(error_code=0))

    @staticmethod
    def click(device_label, x, y, z):
        click_orders = ['G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x, y, 0, MOVE_SPEED - 10000),
                        'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x, y, z, MOVE_SPEED - 10000),
                        'G01 X%0.1fY-%0.1fZ%dF%d \r\n' % (x, y, 0, MOVE_SPEED - 10000)]
        hand_serial_obj_dict.get(device_label).send_list_order(click_orders)
        hand_serial_obj_dict.get(device_label).recv()
