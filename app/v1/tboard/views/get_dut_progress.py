from app.v1.tboard.model.dut import Dut
from app.v1.tboard.views import tborad_router


@tborad_router.route('/get_dut_progress/<string:device_label>/')
def get_dut_progress(device_label):
    return get_dut_progress_inner(device_label)


def get_dut_progress_inner(device_label):
    if len(Dut.all(device_label=device_label)) > 0:
        return {"status": "busy"}
    return {"status": "idle"}
