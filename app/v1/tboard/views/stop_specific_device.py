from app.execption.outer.error_code.tboard import DutNotExist
from app.v1.tboard.model.dut import Dut
from app.v1.tboard.views import tborad_router


@tborad_router.route('/stop_specific_device/<string:device_label>/', methods=['DELETE'])
def stop_specific_device(device_label):
    return stop_specific_device_inner(device_label)


def stop_specific_device_inner(device_label):
    dut_list = Dut.all(device_label=device_label)
    if len(dut_list) > 0:
        for dut in dut_list:
            dut.stop_dut()
        return {"status": f"{device_label} stop  device success"}
    raise DutNotExist(description=f"device_label({device_label}) is not in tboard")
