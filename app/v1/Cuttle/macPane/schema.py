import os
import re
import threading
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
from flask import Response, jsonify
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE, validates_schema

from app.config.setting import PROJECT_SIBLING_DIR
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.operator.camera_operator import camera_start

from app.v1.device_common.device_model import Device
from app.execption.outer.error_code.camera import CameraInUse
from redis_init import redis_client


def validate_ip(ip):
    IP_REGEX = re.compile(r'((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})(\.((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})){3}')
    if not IP_REGEX.match(ip):
        raise ValidationError('ip address must have correct format')


lock = threading.Lock()


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
            from app.v1.Cuttle.basic.setting import camera_dq_dict
            src = camera_dq_dict.get(device_label).pop()
            # image = cv2.imdecode(src, 1)
            image = np.rot90(src, 3)
            # src = CameraHandler.get_roi(device_label, image)
            cv2.imwrite(image_path, image)
        else:
            jsdata = dict({"requestName": "AddaExecBlock", "execBlockName": "snap_shot",
                           "execCmdList": [
                               f"adb -s {device_obj.connect_number} exec-out screencap -p > {image_path}"
                           ],
                           "device_label": device_label})
            snap_shot_result = UnitFactory().create("AdbHandler", jsdata)
            if 0 != snap_shot_result.get('result'):
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
    device_label = fields.String(required=True)
    high_exposure = fields.Integer(required=False)

    class Meta:
        unknown = INCLUDE

    @post_load
    def make_sure(self, data, **kwargs):
        # 相机正在获取图片的时候 不能再次使用
        if redis_client.get("g_bExit") == "0":
            raise CameraInUse()

        path = "original.png"
        device_obj = Device(pk=data.get("device_label"))
        executer = ThreadPoolExecutor()
        future = executer.submit(camera_start, 1, device_obj, high_exposure=data.get('high_exposure'))
        for _ in as_completed([future]):
            self.get_snap_shot(data.get("device_label"), path)
            f = open(path, "rb")
            image = f.read()
            return Response(image, mimetype="image/jpeg")

    @staticmethod
    def get_snap_shot(device_label, path):
        from app.v1.Cuttle.basic.setting import camera_dq_dict
        src = camera_dq_dict.get(device_label)[-1]
        # image = cv2.imdecode(src, 1)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        cv2.imwrite(path, src)
        return 0


class CoordinateSchema(Schema):
    device_label = fields.String(required=True)
    inside_upper_left_x = fields.Int(required=True)
    inside_upper_left_y = fields.Int(required=True)
    inside_under_right_x = fields.Int(required=True)
    inside_under_right_y = fields.Int(required=True)

    return_x = fields.Int(required=True)
    return_y = fields.Int(required=True)
    desktop_x = fields.Int(required=True)
    desktop_y = fields.Int(required=True)
    menu_x = fields.Int(required=True)
    menu_y = fields.Int(required=True)

    class Meta:
        unknown = INCLUDE

    @post_load
    def make_sure(self, data, **kwargs):
        device_obj = Device(pk=data.get("device_label"))
        redis_client.set("g_bExit", "1")
        time.sleep(1.5)
        device_obj.update_device_border(data)
        executer = ThreadPoolExecutor()
        bias = 16 if data.get("inside_upper_left_x") % 16 > 8 else 0
        w_bias =16 if ((data.get("inside_under_right_x") - data.get("inside_upper_left_x")) % 16) > 8 else 0
        executer.submit(camera_start, 1, device_obj,
                        OffsetX=data.get("inside_upper_left_x") // 16 * 16 + bias,
                        # 120-->2   240-->4
                        OffsetY=data.get("inside_upper_left_y") // 4 * 4,
                        Width=(data.get("inside_under_right_x") - data.get("inside_upper_left_x")) // 16 * 16 + w_bias,
                        Height=(data.get("inside_under_right_y") - data.get("inside_upper_left_y")) // 4 * 4 + 4)
        return jsonify({"status": "success"}), 200
