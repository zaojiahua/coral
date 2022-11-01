import time

from app.config.url import tboard_url, tboard_release_busy_device
from app.libs.http_client import request
from app.v1.tboard.model.tboard import TBoard
from app.config.ip import HOST_IP


# 对比本地的tboard数据和服务器的tboard数据，以服务器的数据为准。
# 1. 如果本地有服务器没有的数据，删除。2. 服务器中有数据，本地没有，设置服务器tboard状态为完成。
# 3. 服务器和本地有同样的没有运行完的tboard，着重对这部分数据进行处理。获取tboard中的dut list列表，判断dut对应的设备状态是否是busy，
# 非busy态删除dut。一个tboard中，如果dut list为空，设置tboard为完成。只要有一个dut是正常的，那么重新开始执行用例。
def tboard_init():
    response = request(url=tboard_url.format(f"?finished_flag=False&fields=id&device__cabinet={int(HOST_IP.split('.')[-1])}"))
    unfinished_tboard_list = [str(tboard.get("id")) for tboard in response.get("tboards") if tboard]

    local_tboards = [tboard.pk for tboard in TBoard.all()]
    remove_tboards = list(set(local_tboards) - set(unfinished_tboard_list))
    for remove_tboard_id in remove_tboards:
        print(f'本地存在服务器上没有运行完的tboard {remove_tboard_id}')
        TBoard(pk=remove_tboard_id).remove()

    for tboard_id in unfinished_tboard_list:
        if TBoard(pk=tboard_id).exist():
            duts = TBoard(pk=tboard_id).dut_list
            for dut in duts.smembers():
                from app.v1.device_common.device_model import Device, DeviceStatus
                device_obj = Device(pk=dut.device_label)
                if device_obj.status != DeviceStatus.BUSY:
                    duts.srem(dut)
                    dut.remove()
                else:
                    print(f'重新开始执行用例 {dut.device_label}')
                    time.sleep(30)
                    # 这里有一小点问题，当上一个任务恰好执行完毕，提交了rds以后容器重启的话，current_job_index不应该减1
                    dut.current_job_index -= 1
                    dut.start_dut()
            # t_board中如果没有可以执行的dut 则结束 不需要设置设备状态 因为都不是busy
            if TBoard(pk=tboard_id).dut_list.scard() == 0:
                TBoard(pk=tboard_id).send_tborad_finish()
        else:
            print(f'本地不存在该tboard {tboard_id}')
            TBoard.notify_tboard_finish(tboard_id)
            # 将busy状态的设置为idle
            request(method='POST', url=tboard_release_busy_device, json={'tboard_id': tboard_id})
