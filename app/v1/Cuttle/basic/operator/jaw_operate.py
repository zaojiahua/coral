from app.v1.Cuttle.basic.operator.handler import Handler
from app.v1.Cuttle.basic.operator.hand_operate import get_hand_serial_key
from app.v1.Cuttle.basic.setting import jaw_serial_obj_dict, MAX_WIDTH
from app.v1.Cuttle.basic.jaw_serial import JawSerial


def jaw_init(jaw_com, device_obj):
    jaw_key = get_hand_serial_key(device_obj.pk, jaw_com)
    jaw_serial_obj = JawSerial(timeout=5)
    jaw_serial_obj.connect(jaw_com)
    jaw_serial_obj_dict[jaw_key] = jaw_serial_obj
    jaw_serial_obj.set_jaw_to_spec_width(MAX_WIDTH)
    return jaw_serial_obj.recv_reply()


class JawHandler(Handler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def before_execute(self):
        pass

