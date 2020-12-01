from app.config import ip
from app.v1.Cuttle.network import network_setting
from app.v1.Cuttle.network.network_setting import logger
from app.v1.Cuttle.network.router_model import Router
from app.v1.Cuttle.network.router_model_2 import NewRouter
from app.v1.device_common.device_model import Device

"""
每个api进来都先验证stok 和 cookie是否可用，如果返回-1 那么证明此时network_setting存在错误，network无法提供任何服务
即任何api都无法执行成功，此时：所有的api都会对输入参数进行一次log记录 并返回-1
"""


def judge_router_version():
    try:
        return ip.ROUTER_TYPE
    except AttributeError as e:
        return 0


router_type = judge_router_version()


def bind_spec_ip(spec_ip, device_label):
    if router_type == 1:
        return new_bind_spec_ip(spec_ip, device_label)
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if Router.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        ret = Router.bind_ip(Router.spec_ip_info(spec_ip, Router.client_table()))
        network_setting.is_route_using = False
        logger.debug(f"bind_ip:{spec_ip} result is {ret}")
        if ret == 0: Device(pk=device_label).is_bind = True
        return ret


def new_bind_spec_ip(spec_ip, device_label):
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if NewRouter.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        ret = NewRouter.bind_ip(spec_ip)
        network_setting.is_route_using = False
        logger.debug(f"bind_ip:{spec_ip} result is {ret}")
        if ret == 0: Device(pk=device_label).is_bind = True
        return ret


def unbind_spec_ip(spec_ip):
    if router_type == 1:
        return new_unbind_spec_ip(spec_ip)
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if Router.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        # 此时stok，cookie可用，进行解绑ip操作
        ret = Router.unbind_ip(spec_ip, Router.static_table())
        network_setting.is_route_using = False
        return ret


def new_unbind_spec_ip(spec_ip):
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if NewRouter.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        # 此时stok，cookie可用，进行解绑ip操作
        ret = NewRouter.unbind_ip(spec_ip)
        network_setting.is_route_using = False
        return ret


def batch_bind_ip(list_ip_info):
    """
    :param list_ip_info: dict
    eg:
        {
            "10.80.5.123":"device_label"
        }
    :return:
    """
    if router_type == 1:
        return new_batch_bind_ip(list_ip_info)
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if Router.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        client_list = Router.client_table()
        for ip, device_label in list_ip_info.items():
            ret = Router.bind_ip(Router.spec_ip_info(ip, client_list))
            logger.debug(f"bind_ip:{ip} result is {ret}")
            if ret == 0: Device(pk=device_label).is_bind = True
        network_setting.is_route_using = False
        return 0


def new_batch_bind_ip(list_ip_info):
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if NewRouter.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        for ip, device_label in list_ip_info.items():
            ret = NewRouter.bind_ip(ip)
            logger.debug(f"bind_ip:{ip} result is {ret}")
            if ret == 0: Device(pk=device_label).is_bind = True
        network_setting.is_route_using = False
        return 0


def batch_unbind_ip(ip_list):
    """
    :param ip_list:
    :return:
    ps: IP解绑失败返回-1
        如果未在静态列表中找到指定IP也会返回-1
    """
    if router_type == 1:
        return new_batch_unbind_ip(ip_list)
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if Router.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        static_list = Router.static_table()
        for ip in ip_list:
            ret = Router.unbind_ip(ip, static_list)
            logger.debug(f"unbind_ip:{ip} result is {ret}")
        network_setting.is_route_using = False
        return 0


def new_batch_unbind_ip(ip_list):
    while not network_setting.is_route_using:
        network_setting.is_route_using = True
        if NewRouter.vertify_stok_is_available() == -1:
            logger.error("network setting  has an error the router's message.")
            return -1
        for ip in ip_list:
            ret = NewRouter.unbind_ip(ip)
            logger.debug(f"unbind_ip:{ip} result is {ret}")
        network_setting.is_route_using = False
        return 0


if __name__ == '__main__':
    js_data = {
        "10.81.2.4": "lable",
        "10.81.2.5": "lable"
    }
    ip_list = ["10.81.2.2", "10.81.2.4"]
    ret = batch_unbind_ip(ip_list)
    # ret = batch_bind_ip(js_data)
    print(ret)
