from app.config.setting import arm_com_jaw, arm_com_1_jaw
from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.operator.hand_operate import get_hand_serial_key
from app.v1.Cuttle.basic.setting import jaw_serial_obj_dict, MAX_WIDTH, normal_result
from app.v1.Cuttle.basic.jaw_serial import JawSerial


def jaw_init(jaw_com, device_obj, **kwargs):
    jaw_key = get_hand_serial_key(device_obj.pk, jaw_com)
    jaw_serial_obj = JawSerial(timeout=5)
    jaw_serial_obj.connect(jaw_com)
    jaw_serial_obj_dict[jaw_key] = jaw_serial_obj
    jaw_serial_obj.set_jaw_to_spec_width(MAX_WIDTH)
    return jaw_serial_obj.recv_reply()


class JawHandler(Handler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def before_execute(self, *args, **kwargs):
        return normal_result

    def str_func(self, exec_content, *args, **kwargs):
        """
        2023.03.06 目前电爪只支持了一个动作，即闭合或者打开，故这里简单处理
        """
        jaw_com = arm_com_jaw if exec_content.split(" ")[0].strip() == 0 else arm_com_1_jaw
        target_value = exec_content.split(" ")[2].strip()
        jaw_serial_obj = jaw_serial_obj_dict[get_hand_serial_key(self._model.pk, jaw_com)]
        jaw_serial_obj.set_jaw_to_spec_width(target_value)
        return jaw_serial_obj.recv_reply()
