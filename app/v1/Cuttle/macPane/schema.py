import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Response, jsonify
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE
import numpy as np
import cv2

from app.config.setting import PROJECT_SIBLING_DIR
from app.v1.Cuttle.basic.operator.camera_operator import camera_start

from app.v1.device_common.device_model import Device
from app.config.setting import CORAL_TYPE
from redis_init import redis_client
from app.v1.eblock.model.unit import get_assist_device_ident
from app.v1.Cuttle.basic.setting import get_global_value, set_global_value


def validate_ip(ip):
    IP_REGEX = re.compile(r'((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})(\.((2(5[0-5]|[0-4]\d))|[0-1]?\d{1,2})){3}')
    if not IP_REGEX.match(ip):
        raise ValidationError('ip address must have correct format')


lock = threading.Lock()


class PaneSchema(Schema):
    picture_name = fields.String(missing="snap.png")
    device_label = fields.String(required=True)
    device_ip = fields.String(required=True, validate=validate_ip)
    assist_device = fields.Integer(required=False)
    camera_rotate = fields.Integer(required=False)

    @post_load
    def make_sure(self, data, **kwargs):
        picture_name = data.get("picture_name")
        device_label = data.get("device_label")
        assist_device = data.get('assist_device')

        # 如果传过来的旋转角度和设置的值不一样，则按照传过来的值旋转，如果一样，就不需要动了
        camera_rotate = data.get('camera_rotate')
        default_camera_rotate = get_global_value('camera_rotate')
        try:
            camera_rotate = int(camera_rotate)
            if camera_rotate == -1:
                camera_rotate = default_camera_rotate
        except Exception:
            camera_rotate = default_camera_rotate

        # 对图片进行旋转
        set_global_value('camera_rotate', camera_rotate)

        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=device_label)
        if not str.endswith(picture_name, (".png", ".jpg")):
            picture_name = picture_name + ".jpg"
        folder_path = os.path.join(PROJECT_SIBLING_DIR, "Pacific", data.get("device_label"), "jobEditor")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        image_path = os.path.join(folder_path, picture_name)

        assist_device_ident = get_assist_device_ident(device_label, assist_device) \
            if assist_device is not None else None

        # 返回的数据格式需要和异常时候的统一
        ret_code = device_obj.get_snapshot(image_path, connect_number=assist_device_ident, max_retry_time=1)
        if ret_code == 0:
            try:
                with open(image_path, 'rb') as f:
                    image = f.read()
                    resp = Response(image, mimetype="image/jpeg")
                    return resp
            except Exception as e:
                print(repr(e))
            finally:
                os.remove(image_path)
                set_global_value('camera_rotate', default_camera_rotate)
        else:
            return jsonify({"status": ret_code}), 400


class OriginalPicSchema(Schema):
    device_label = fields.String(required=True)
    high_exposure = fields.Integer(required=False)

    class Meta:
        unknown = INCLUDE

    @post_load
    def make_sure(self, data, **kwargs):
        path = "original.png"
        device_obj = Device(pk=data.get("device_label"))
        try:
            ret_code = device_obj.get_snapshot(path, data.get('high_exposure'), True)
            if ret_code == 0:
                f = open(path, "rb")
                image = f.read()
                return Response(image, mimetype="image/jpeg")
        except Exception as e:
            return {'description': str(e)}, 400


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


class ClickTestSchema(Schema):
    device_label = fields.String(required=True)
    inside_upper_left_x = fields.Int(required=True)
    inside_upper_left_y = fields.Int(required=True)
    inside_under_right_x = fields.Int(required=True)
    inside_under_right_y = fields.Int(required=True)
    x = fields.Float(required=True)
    y = fields.Float(required=True)
    z = fields.Float(required=True)
    click_count = fields.Int(required=False)
    stop_loop_flag = fields.Bool(required=False)

    class Meta:
        unknown = INCLUDE
