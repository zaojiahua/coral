from app.config.url import tboard_url, tboard_release_busy_device
from app.libs.http_client import request
from app.v1.tboard.model.tboard import TBoard
from app.config.ip import HOST_IP


def tboard_init():
    response = request(url=tboard_url.format(f"?finished_flag=False&fields=id&device__cabinet={int(HOST_IP.split('.')[-1])}"))
    unfinished_tboard_list = [str(tboard.get("id")) for tboard in response.get("tboards") if tboard]
    for tboard_id in unfinished_tboard_list:
        try:
            TBoard(pk=tboard_id).send_tborad_finish()
        except:
            pass
    for tboard in TBoard.all():
        tboard.remove()
    # 将busy状态的设置为idle
    for tboard_id in unfinished_tboard_list:
        request(method='POST', url=tboard_release_busy_device, json={'tboard_id': tboard_id})
