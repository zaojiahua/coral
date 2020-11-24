from flask import jsonify, request
from flask.views import MethodView

from app.v1.Cuttle.paneDoor.door_keeper import DoorKeeper
from app.v1.device_common.device_model import Device


class DeviceBase(MethodView):
    def __init__(self):
        super(DeviceBase, self).__init__()
        self.door_keeper = DoorKeeper()


class GetDevice(DeviceBase):
    def get(self):
        respnse_body = self.door_keeper.get_device_info_compatibility()
        return jsonify(respnse_body), 200

class GetAssisDevice(DeviceBase):
    def get(self):
        respnse_body = self.door_keeper.get_assis_device()
        return jsonify(respnse_body), 200

class SetAssisDevice(DeviceBase):
    def post(self):
        data = request.get_json()
        self.door_keeper.set_assis_device(**data)
        return jsonify({"state": "DONE"}), 200

class SetDevice(DeviceBase):
    def post(self):
        data = request.get_json()
        # todo validate data first
        self.door_keeper.authorize_device(**data)
        return jsonify({"state": "DONE"}), 200

class SetDeviceManual(DeviceBase):
    "phone_model_name, device_width, device_height, screen_size, device_name, x_border, y_border"
    def post(self):
        try:
            data = request.get_json()
            self.door_keeper.authorize_device_manually(**data)
            return jsonify({"state": "DONE"}), 200
        except (AttributeError,ValueError) as e:
            print(repr(e))
            return jsonify({"state": "Fail"}), 400


class GetMutiDevice(DeviceBase):
    def get(self):
        respnse_body = self.door_keeper.get_mutidevice_list()
        return jsonify({"total_device_number": len(respnse_body)}), 200

class SetMutiDevice(DeviceBase):
    def post(self):
        data = request.get_json()
        res = self.door_keeper.muti_register(data.get("deviceName"))
        return jsonify(res), 200

class OpenPort(DeviceBase):
    def post(self):
        if 0 == self.door_keeper.reconnect_device(request.get_json().get("cpu_id")):
            return jsonify({"state": "DONE"}), 200
        else:
            return jsonify({"state": "Fail"}), 400





