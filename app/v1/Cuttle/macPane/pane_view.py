import logging
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from flask import request, jsonify, Response
from flask.views import MethodView
from serial import SerialException

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import SUCCESS_PIC_NAME, FAIL_PIC_NAME, LEAVE_PIC_NAME, PANE_LOG_NAME, DEVICE_BRIGHTNESS
from app.execption.outer.error_code.adb import DeviceBindFail
from app.execption.outer.error_code.camera import ArmReInit, NoCamera, NoArm, RemoveBeforeAdd
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import camera_start_3
from app.v1.Cuttle.basic.operator.hand_operate import hand_init, rotate_hand_init
from app.v1.Cuttle.basic.operator.handler import Dummy_model
from app.v1.Cuttle.basic.setting import hand_serial_obj_dict
from app.v1.Cuttle.macPane.schema import PaneSchema, OriginalPicSchema, CoordinateSchema
from app.v1.Cuttle.network.network_api import unbind_spec_ip
from app.v1.device_common.device_model import Device
from app.v1.tboard.views.get_dut_progress import get_dut_progress_inner
from app.v1.tboard.views.stop_specific_device import stop_specific_device_inner
from redis_init import redis_client

logger = logging.getLogger(PANE_LOG_NAME)
from concurrent.futures._base import TimeoutError
import copy
from app.config.setting import CORAL_TYPE

# mapping_dict = {0: ADB_SERVER_1, 1: ADB_SERVER_2, 2: ADB_SERVER_3}


ip = copy.copy(HOST_IP)


def pic_push(device_object, pic_name="success.png"):
    pic_ip = ip.replace("100", "138") if sys.platform.startswith("win") else ip
    jsdata = {
        "execBlockName": "set_config_success",
        "ip_address": device_object.ip_address,
        "device_label": device_object.device_label,
        "execCmdList": [
                        "adb -s " + device_object.ip_address + f":5555 shell am start -a android.intent.action.VIEW -d http://{pic_ip}:5000/static/{pic_name}"]

    }
    if pic_name == LEAVE_PIC_NAME:
        jsdata["execCmdList"].append(f"adb disconnect {device_object.ip_address}")
    pic_push_result = UnitFactory().create("AdbHandler", jsdata)
    logger.info(f"picture push result for {pic_name}'s result :{pic_push_result}")


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
            # if res != 0:
            #     raise DeviceBindFail
        return jsonify({"status": "success"}), 200


    def _reset_arm(self,device_object):
        try:
            hand_serial_obj = hand_serial_obj_dict[device_object.pk]
            hand_serial_obj.send_single_order("G01 X0Y0Z0F1000 \r\n")
            hand_serial_obj.recv(buffer_size=64)
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


class PaneConfigView(MethodView):


    def post(self):
        data = request.get_json()
        executer = ThreadPoolExecutor()
        if data.get("camera_id") is not None:
            self.hardware_init(data.get("camera_id"), data.get("device_label"), executer, rotate=False)
        if data.get("arm_id"):
            self.hardware_init(data.get("arm_id"), data.get("device_label"), executer, rotate=False)
        if data.get("rotate_arm_id"):
            self.hardware_init('rotate', data.get("device_label"), executer, rotate=True)
        return jsonify({"status": "success"}), 200

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
        port = f'/dev/{port}' if platform.system() == 'Linux' else port
        try:
            device_object = Device(pk=device_label)
            if rotate is True:
                function, attribute = (rotate_hand_init, "has_rotate_arm")
            elif port.split("/")[-1].isdigit():
                function, attribute = (camera_start_3, "has_camera")
            else:
                function, attribute = (hand_init, "has_arm")
            setattr(device_object, attribute, True)
            future = executer.submit(function, port, device_object,init=True)
            exception = future.exception(timeout=2)
            if "PermissionError" in str(exception):
                raise ArmReInit
            elif "FileNotFoundError" in str(exception):
                return 0
            elif "tolist" in str(exception):
                raise NoCamera
        except TimeoutError:
            print('TimeoutError')
            return 0

    def delete(self):
        try:
            device_object = Device(pk=request.get_json().get("device_label"))
            device_object.has_arm = False
            device_object.has_camera = False
            hand_serial_obj_dict.get(request.get_json().get("device_label")).close()
            return "success", 204
        except AttributeError:
            raise RemoveBeforeAdd


class PaneBorderView(MethodView):
    def post(self):
        schema = CoordinateSchema()
        return schema.load(request.get_json())


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
