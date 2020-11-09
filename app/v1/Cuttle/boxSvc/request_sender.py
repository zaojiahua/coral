from typing import List
import time
from app.config.ip import HOST_IP
from app.config.url import box_url, device_temper_url
from app.libs.coral_socket import CoralSocket
from app.libs.http_client import request
from app.v1.Cuttle.boxSvc.box_setting import power_retry_times


def send_order(ip, port, order, method):
    # 向继电器发送指令
    if method == "socket":
        return _send_order_by_socket(ip, port, order)
    else:
        return _send_order_by_http()


def _send_order_by_socket(ip, port, order):
    # 通过socket长连接发送指令
    for i in range(power_retry_times):
        with CoralSocket(port=port) as s:
            s.connect(ip)
            s.send(order)
            response = s.recv()
            if "fe" not in response or len(response) < 3:
                continue
            else:
                return response
        time.sleep(0.5)
    return ""


def _send_order_by_http():
    # need to do when we have third version power hardware
    pass


def check_from_reef() -> List:
    response = request(url=box_url, params={"cabinet": HOST_IP.split(".")[-2]})
    return response.get("woodenbox")


def send_available_port_to_reef(total_verfied_list):
    # finished when reef have this api
    pass


def send_temper_to_reef(data_list):
    return request(method='POST', url=device_temper_url, json=data_list)
