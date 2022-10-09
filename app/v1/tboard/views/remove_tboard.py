from concurrent.futures import ThreadPoolExecutor, wait

from flask import jsonify

from app.execption.outer.error_code.tboard import TboardNotExist, TboardStopping
from app.execption.outer.error_code.total import DeleteSuccess
from app.v1.tboard.config.setting import MAX_CONCURRENT_NUMBER
from app.v1.tboard.model.tboard import TBoard
from app.v1.tboard.views import tborad_router
from app.config.setting import tboard_mapping

"""
{
    "boardName":"2019_09_09_19_06_12",
    "ownerID":"3"
}
"""


@tborad_router.route('/remove_tboard/<int:tboard_id>/', methods=['DELETE'])
def remove_tboard(tboard_id):
    return remove_tboard_inner(tboard_id)

# 根据 tboard_id 停止tboard
def remove_tboard_inner(tboard_id, manual_stop=True):
    tboard = TBoard(pk=tboard_id)
    if tboard.exist():
        if tboard.status == "stop":
            # force to stop
            raise TboardStopping()

        tboard.status = "stop"
        executor = ThreadPoolExecutor(MAX_CONCURRENT_NUMBER)
        all_task = []
        for dut in tboard.dut_list.smembers():
            # 抛异常导致后面的stop_flag不能被设置成True 导致tboard 停止失败，用ThreadPoolExecutor既可以捕获异常还可以提高效率
            all_task.append(executor.submit(dut.stop_dut, manual_stop))
        wait(all_task)
        response_data = dict(code=204, data=tboard_mapping.get(tboard_id, {}))
        print('返回给reef的数据')
        print(response_data)
        return jsonify(response_data)

    raise TboardNotExist(description=f"tboard {tboard_id} is not exist")


@tborad_router.route('/force_remove_tboard/<int:tboard_id>/', methods=['DELETE'])
def force_remove_tboard(tboard_id):
    tboard = TBoard(pk=tboard_id)
    if tboard.hash_exist():
        tboard.send_tborad_finish()
        return DeleteSuccess()

    return TboardNotExist(description=f"tboard {tboard_id} is not exist")
