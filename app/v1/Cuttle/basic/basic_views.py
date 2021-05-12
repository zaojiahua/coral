from flask import request, jsonify

from flask.views import MethodView

from app.libs.log import setup_logger
from app.v1.Cuttle.basic.model import HandDevice, AdbDevice
# 下面5条不可去掉
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import CameraHandler
from app.v1.Cuttle.basic.operator.complex_operator import ComplexHandler
from app.v1.Cuttle.basic.operator.hand_operate import HandHandler
from app.v1.Cuttle.basic.operator.image_operator import ImageHandler
from app.v1.Cuttle.basic.operator.handler import Dummy_model
from app.v1.Cuttle.basic.operator.image_operator import ImageHandler


# 每一个相同的底层unit都有6种情况：

#  主机unit -->  ADB执行unit             1主机有线执行
#                                      2主机无线执行
#               机械臂执行unit           3机械臂执行
#               摄像头执行unit           4摄像头执行

#  僚机unit -->  ADB执行unit            5僚机有线执行
#                                      6僚机无线执行
# 另外主僚机的每个复合型unit 也可以再下分这6种情况.

# 坐标的换算有下面多种情况
# 相对坐标/绝对坐标  摄像头下像素坐标/截图中像素坐标/机械臂下物理坐标    裁剪图中坐标/实际图中坐标


class UnitFactory(object):
    model_dict = {
        "HandHandler": HandDevice,
        "AdbHandler": AdbDevice,
        "ComplexHandler": AdbDevice,
    }

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def create(self, handler_type, input_data):
        model = self.model_dict.get(handler_type, Dummy_model)
        pk = input_data.get("device_label")
        model_obj = model(is_busy=False, pk=pk, logger=setup_logger(f'{handler_type}-{pk}', f'{handler_type}-{pk}.log'))
        return eval(handler_type)(model=model_obj, many=isinstance(input_data.get('execCmdList'), list),
                                  **input_data).execute()


class TestIconClass(MethodView):
    def post(self):
        try:
            image_handler = ImageHandler(model=Dummy_model, many=False)
            return jsonify(image_handler.test_icon_exist(request.files)), 200
        except Exception as e:
            return jsonify({"status": repr(e)}), 400


class TestIconPositionClass(MethodView):
    def post(self):
        # try:
            image_handler = ImageHandler(model=Dummy_model, many=False)
            response = image_handler.test_icon_position(request.files)
            return jsonify(response), 200
        # except Exception as e:
        #     return jsonify({"status": repr(e)}), 400

def test_position_fixed():
    image_handler = ImageHandler(model=Dummy_model, many=False)
    response = image_handler.test_icon_position_fixed(request.files)
    return jsonify(response), 200



class TestOcrClass(MethodView):
    def post(self):
        try:
            image_handler = ImageHandler(model=Dummy_model, many=False)
            request_params = {}
            request_params.update(request.files)
            request_params.update(request.form.to_dict())
            return jsonify(image_handler.test_ocr_result(request_params)), 200
        except Exception as e:
            return jsonify({"status": repr(e)}), 400


if __name__ == '__main__':
    test_dict = {
        "execCmdDict": {
            "configArea": {
                "content": "<1ijobFile>Tmach ",
            },
            "configFile": {
                "content": "<1ijobFile>Tmach ",
            },
            "inputImgFile": {
                "content": "<blkOutPath>Tmach ",
            },
            "referImgFile": {
                "content": "<1ijobFile>Tmach ",
            }
        }}
