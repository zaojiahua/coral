import os
import re
from ctypes import cast, POINTER, byref, sizeof, memset, c_ubyte, cdll

import cv2
import numpy as np
from flask import Response, jsonify
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE, validates_schema

from app.config.setting import PROJECT_SIBLING_DIR
from app.v1.Cuttle.basic.MvImport.CameraParams_header import MV_Image_Jpeg, MV_SAVE_IMAGE_PARAM_EX
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.operator.camera_operator import camera_init_HK
from app.v1.device_common.device_model import Device


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
        device_ip = data.get("device_ip")
        device_label = data.get("device_label")
        if not str.endswith(picture_name, (".png", ".jpg")):
            picture_name = picture_name + ".jpg"
        folder_path = os.path.join(PROJECT_SIBLING_DIR, "Pacific", data.get("device_label"), "jobEditor")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        image_path = os.path.join(folder_path, picture_name)
        jsdata = dict({"requestName": "AddaExecBlock", "execBlockName": "snap_shot",
                       "execCmdList": [f"adb -s {device_ip}:5555 shell screencap -p /sdcard/{picture_name}",
                                       f"adb -s {device_ip}:5555 pull /sdcard/{picture_name} {image_path}"],
                       "device_label": device_label})
        jsdata["ip_address"] = data.get("device_ip")
        try:
            from app.v1.device_common.device_model import Device
            snap_shot_result = UnitFactory().create("AdbHandler", jsdata) if not Device(
                pk=device_label).has_camera else UnitFactory().create(
                "CameraHandler", jsdata)
            if {"result": 0} == snap_shot_result:
                with open(image_path, 'rb') as f:
                    image = f.read()
                    resp = Response(image, mimetype="image/jpeg")
                    return resp
            else:
                return jsonify({"status": snap_shot_result}), 400
        finally:
            os.remove(image_path)


class OriginalPicSchema(Schema):
    # device_label = fields.String(required=True)
    camera_id = fields.Int(required=True)

    class Meta:
        unknown = INCLUDE

    @post_load
    def make_sure(self, data, **kwargs):
        path = "original.png"
        self.get_snap_shot(data.get("camera_id"), path)
        f = open(path, "rb")
        image = f.read()
        return Response(image, mimetype="image/jpeg")

    def get_snap_shot(self, camera_id, path):
        # cap = cv2.VideoCapture(camera_id)
        # cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc('M', 'J', 'P', 'G'))
        # cap.set(cv2.CAP_PROP_FPS, 20)
        # cap.set(3, camera_w)
        # cap.set(4, camera_h)
        # ret, frame = cap.read()
        # if frame is None:
        #     cap.release()
        #     raise NoCamera
        # cap.release()
        from app.v1.Cuttle.basic.setting import CamObjList
        data_buf, nPayloadSize, stFrameInfo = camera_init_HK(5)
        cam_obj = CamObjList.pop()
        for i in range(3):
            ret = cam_obj.MV_CC_GetOneFrameTimeout(byref(data_buf), nPayloadSize, stFrameInfo, 1000)
            if ret == 0:
                stParam = MV_SAVE_IMAGE_PARAM_EX()
                m_nBufSizeForSaveImage = stFrameInfo.nWidth * stFrameInfo.nHeight * 3 + 2048
                m_pBufForSaveImage = (c_ubyte * m_nBufSizeForSaveImage)()
                memset(byref(stParam), 0, sizeof(stParam))
                stParam.enImageType = MV_Image_Jpeg
                stParam.enPixelType = stFrameInfo.enPixelType
                stParam.nWidth = stFrameInfo.nWidth
                stParam.nHeight = stFrameInfo.nHeight
                stParam.nDataLen = stFrameInfo.nFrameLen
                stParam.pData = cast(byref(data_buf), POINTER(c_ubyte))
                stParam.pImageBuffer = cast(byref(m_pBufForSaveImage), POINTER(c_ubyte))
                stParam.nBufferSize = m_nBufSizeForSaveImage
                stParam.nJpgQuality = 80
                cam_obj.MV_CC_SaveImageEx2(stParam)
                cdll.msvcrt.memcpy(byref(m_pBufForSaveImage), stParam.pImageBuffer, stParam.nImageLen)
                image = np.asarray(m_pBufForSaveImage, dtype="uint8")
                src = cv2.imdecode(image, 1)
                break
            else:
                continue
        try:
            os.remove(path)
            cv2.imwrite(path, src)
            return 0
        except FileNotFoundError:
            pass
        finally:
            cam_obj.MV_CC_CloseDevice()


class CoordinateSchema(Schema):
    device_label = fields.String(required=True)
    inside_upper_left_x = fields.Float(required=True)
    inside_upper_left_y = fields.Float(required=True)
    outside_upper_left_x = fields.Float(required=True)
    outside_upper_left_y = fields.Float(required=True)
    inside_under_right_x = fields.Float(required=True)
    inside_under_right_y = fields.Float(required=True)
    outside_under_right_y = fields.Float(required=True)
    outside_under_right_x = fields.Float(required=True)

    class Meta:
        unknown = INCLUDE

    @validates_schema
    def validate_numbers(self, data, **kwargs):
        if data["inside_upper_left_x"] < data["outside_upper_left_x"] or data["outside_under_right_y"] < data[
            "inside_under_right_y"]:
            raise ValidationError("border should bigger than 0")



    @post_load
    def make_sure(self, data, **kwargs):
        device_obj = Device(pk=data.get("device_label"))
        device_obj.update_device_border(data)
        return jsonify({"status": "success"}), 200
