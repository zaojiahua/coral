from flask import jsonify

from app.execption.outer.error_code.tboard import DutNotExist
from app.v1.tboard.model.dut import Dut
from app.v1.tboard.views import tborad_router


@tborad_router.route('/stop_specific_device/<string:device_label>/', methods=['DELETE'])
def stop_specific_device(device_label):
    return stop_specific_device_inner(device_label)


# 停止单个device 执行的 dut
def stop_specific_device_inner(device_label):
    dut_list = Dut.all(device_label=device_label)
    if len(dut_list) > 0:
        for dut in dut_list:
            dut.stop_dut(False if len(dut_list) == 1 else True)
        return jsonify(dict(error_code=0, description=f'设备停止成功'))
    # busy 状态的device肯定有dut
    raise DutNotExist(description=f"该设备({device_label})未在运行")
