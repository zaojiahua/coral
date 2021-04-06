import os
import re
import time
from concurrent.futures.thread import ThreadPoolExecutor

import cv2
from flask import Response, jsonify
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE, validates_schema

from app.config.setting import PROJECT_SIBLING_DIR
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.operator.camera_operator import camera_start_3
from app.v1.Cuttle.basic.setting import camera_dq_dict
from app.v1.device_common.device_model import Device
from redis_init import redis_client


def validate_ip(ip):
    IP_REGEX = re.compile(r'((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})(\.((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})){3}')
    if not IP_REGEX.match(ip):
        raise ValidationError('ip address must have correct format')


class PaneSchema(Schema):
    picture_name = fields.String(missing="snap.png")
    device_label = fields.String(required=True)
    device_ip = fields.String(required=True, validate=validate_ip)

    @post_load
    def make_sure(self, data, **kwargs):
        picture_name = data.get("picture_name")
        # device_ip = data.get("device_ip")
        device_label = data.get("device_label")
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=device_label)
        if not str.endswith(picture_name, (".png", ".jpg")):
            picture_name = picture_name + ".jpg"
        folder_path = os.path.join(PROJECT_SIBLING_DIR, "Pacific", data.get("device_label"), "jobEditor")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        image_path = os.path.join(folder_path, picture_name)
        # 禁止adb 有线模式下的editor 流程暂时不启用，有线模式下暂时允许通过有线截图
        # if ADB_TYPE == 1:
        #     src = Image.new("RGB", (300, 600), (255, 255, 255))
        #     src = np.array(src)
        #     cv2.putText(src, "Please edit on a wireless device", (0, 200), cv2.FONT_HERSHEY_SIMPLEX,
        #                 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        #     cv2.imwrite(image_path, src)
        #     with open(image_path, 'rb') as f:
        #         image = f.read()
        #         return Response(image, mimetype="image/jpeg")

        if device_obj.has_camera:
            from app.v1.Cuttle.basic.operator.camera_operator import CameraHandler
            src = camera_dq_dict.get(device_label)[-1]
            image = cv2.imdecode(src, 1)
            src = CameraHandler.get_roi(device_label, image)
            cv2.imwrite(image_path, src)
        else:
            jsdata = dict({"requestName": "AddaExecBlock", "execBlockName": "snap_shot",
                           "execCmdList": [
                               f"adb -s {device_obj.connect_number} shell screencap -p /sdcard/{picture_name}",
                               f"adb -s {device_obj.connect_number} pull /sdcard/{picture_name} {image_path}"
                           ],
                           "device_label": device_label})
            snap_shot_result = UnitFactory().create("AdbHandler", jsdata)
            if {"result": 0} != snap_shot_result:
                return jsonify({"status": snap_shot_result}), 400
        try:
            with open(image_path, 'rb') as f:
                image = f.read()
                resp = Response(image, mimetype="image/jpeg")
                return resp
        except Exception as e:
            print(repr(e))
        finally:
            os.remove(image_path)


class OriginalPicSchema(Schema):
    # device_label = fields.String(required=True)
    device_label = fields.String(required=True)

    class Meta:
        unknown = INCLUDE

    @post_load
    def make_sure(self, data, **kwargs):
        path = "original.png"
        device_obj = Device(pk=data.get("device_label"))
        redis_client.set("g_bExit", "1")
        time.sleep(0.5)
        executer = ThreadPoolExecutor()
        executer.submit(camera_start_3, 1, device_obj)
        time.sleep(0.5)
        self.get_snap_shot(data.get("device_label"), path)
        f = open(path, "rb")
        image = f.read()
        return Response(image, mimetype="image/jpeg")

    def get_snap_shot(self, device_label, path):
        src = camera_dq_dict.get(device_label)[-1]
        image = cv2.imdecode(src, 1)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        cv2.imwrite(path, image)
        return 0


class CoordinateSchema(Schema):
    device_label = fields.String(required=True)
    inside_upper_left_x = fields.Int(required=True)
    inside_upper_left_y = fields.Int(required=True)
    outside_upper_left_x = fields.Int(required=True)
    outside_upper_left_y = fields.Int(required=True)
    inside_under_right_x = fields.Int(required=True)
    inside_under_right_y = fields.Int(required=True)
    outside_under_right_y = fields.Int(required=True)
    outside_under_right_x = fields.Int(required=True)

    class Meta:
        unknown = INCLUDE

    @validates_schema
    def validate_numbers(self, data, **kwargs):
        if data["inside_upper_left_x"] < data["outside_upper_left_x"] or data["outside_under_right_y"] < data[
            "inside_under_right_y"]:
            raise ValidationError("border should bigger than 0")

    @post_load
    def make_sure(self, data, **kwargs):
        print(data)
        device_obj = Device(pk=data.get("device_label"))
        redis_client.set("g_bExit", "1")
        time.sleep(1)
        executer = ThreadPoolExecutor()
        executer.submit(camera_start_3, 1, device_obj,
                       OffsetX=data.get("inside_upper_left_x")//16 *16,
                       OffsetY=data.get("inside_upper_left_y")//2 *2 + 200,
                       Width=(data.get("inside_under_right_x") - data.get("inside_upper_left_x"))//16 *16,
                       Height=(data.get("inside_under_right_y") - data.get("inside_upper_left_y"))//2 *2)
        # device_obj.update_device_border(data)
        return jsonify({"status": "success"}), 200
