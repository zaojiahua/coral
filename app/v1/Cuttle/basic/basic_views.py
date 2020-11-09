import traceback

from app.libs.log import setup_logger
from app.v1.Cuttle.basic.model import HandDevice, AdbDevice
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.basic.operator.camera_operator import CameraHandler
from app.v1.Cuttle.basic.operator.complex_operator import ComplexHandler
from app.v1.Cuttle.basic.operator.hand_operate import HandHandler
from app.v1.Cuttle.basic.operator.image_operator import ImageHandler
from app.v1.Cuttle.basic.operator.handler import Dummy_model


# ------入口函数，使用with表达式生明对应handler和device，并显式调用execute方法-----

#
# # 机械臂入口函数
# def mechanical_arm(input_data):
#     # 机械臂 放置多台设备后，此处换成pane id
#     hand_device = HandDevice(pk=input_data.get("device_label"))
#     with HandHandler(model=hand_device, many=isinstance(input_data['execCmdList'], list), **input_data) as h:
#         return h.execute()
#
#
# # adb入口函数
# def adb_exec(input_data):
#     device = AdbDevice(pk=input_data.get("device_label"))
#     with AdbHandler(model=device, many=isinstance(input_data['execCmdList'], list), **input_data) as h:
#         return h.execute()
#
#
# # 摄像头入口函数
# def camera_exec(input_data):
#     model = Dummy_model(False, input_data.get("device_label"), setup_logger(f'camera', 'camera.log'))
#     handler = CameraHandler(model=model, many=isinstance(input_data['execCmdList'], list), **input_data)
#     return handler.execute()
#
#
# # 图像分析入口函数
# def image_exec(input_data):
#     device_label = input_data.get("device_label")
#     model = Dummy_model(False, device_label, setup_logger(f'imageTool-{device_label}', f'imageTool-{device_label}.log'))
#     image_handler = ImageHandler(model=model, **input_data)
#     return image_handler.execute()
#
#
# # 复合unit入口函数
# def complex_unit(input_data):
#     model = Dummy_model(False, input_data.get("device_label"), setup_logger(f'complex', 'complex.log'))
#     complex_handler = ComplexHandler(model=model, **input_data)
#     return complex_handler.execute()


class UnitFactory(object):
    model_dict = {
        "HandHandler": HandDevice,
        "AdbHandler": AdbDevice,
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
