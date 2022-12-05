import time

import traceback

from flask import request, jsonify

# 下面5条不可去掉,因为是要靠eval实例化的类
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import CameraHandler
from app.v1.Cuttle.basic.operator.complex_operator import ComplexHandler
from app.v1.Cuttle.basic.operator.hand_operate import HandHandler
from app.v1.Cuttle.basic.operator.image_operator import ImageHandler
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
from app.v1.Cuttle.basic.url import basic


class UnitFactory(object):
    def __new__(cls, *args, **kwargs):
        # 确保自己为单例对象
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    @staticmethod
    def create(handler_type, input_data) -> dict:
        # 所有unit的入口文件
        pk = input_data.get("device_label")
        # 标记是哪个handler进行的处理，针对不同的handler，在基类中做不同的操作
        input_data['handler_type'] = handler_type
        from app.v1.device_common.device_model import Device
        model_obj = Device(pk=pk)
        time.sleep(input_data.get("before_exec_sleep", 0))
        # 此处，会根据handler_type(是个字符串)实例化一个对应的handler（eg:AdbHandler,ImageHandler），并把刚刚的model，
        # 和执行中unit的信息（input_data）传入handler的构造函数，并显示的调用execute方法。
        return eval(handler_type)(model=model_obj, many=isinstance(input_data.get('execCmdList'), list),
                                  **input_data).execute()


# 下面的都为cypress编辑时，点击测试按钮的执行api
@basic.route('/icon_test/', methods=['POST'])
def test_icon_exist():
    try:
        image_handler = ImageHandler(many=False)
        return jsonify(image_handler.test_icon_exist(request.files)), 200
    except Exception as e:
        return jsonify({"status": repr(e)}), 400


@basic.route('/icon_test_fixed/', methods=['POST'])
def test_icon_exist_fixed():
    try:
        image_handler = ImageHandler(many=False)
        return jsonify(image_handler.test_icon_exist_fixed(request.files)), 200
    except Exception as e:
        return jsonify({"status": repr(e)}), 400


@basic.route('/icon_test_position/', methods=['POST'])
def test_position():
    image_handler = ImageHandler(many=False)
    response = image_handler.test_icon_position(request.files)
    return jsonify(response), 200


@basic.route('/icon_test_position_fixed/', methods=['POST'])
def test_position_fixed():
    image_handler = ImageHandler(many=False)
    response = image_handler.test_icon_position_fixed(request.files)
    return jsonify(response), 200


@basic.route('/ocr_test/', methods=['POST'])
def ocr_test():
    try:
        image_handler = ImageHandler(many=False)
        request_params = {}
        request_params.update(request.files)
        request_params.update(request.form.to_dict())
        return jsonify(image_handler.test_ocr_result(request_params)), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": repr(e)}), 400
