import json

import requests

from app.v1.Cuttle.network import network_setting
from app.v1.Cuttle.network.vertify_response import VertifyResponse
from app.v1.Cuttle.network.network_setting import USERNAME, PASSWORD, logger, ROUTER_IP


class Router:
    host = ROUTER_IP

    def __init__(self):
        pass

    @classmethod
    def origin(cls):
        return f"http://{cls.host}"

    @classmethod
    def stok_referer(cls):
        return f"http://{cls.host}/webpages/login.html"

    @classmethod
    def opt_referer(cls):
        return f"http://{cls.host}/webpages/index.html"

    @classmethod
    def stok_headers(cls):
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Content-Length": "375",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": "c3601be5521a3c6c686b075c5807da3f",
            "Host": cls.host,
            "Referer": cls.stok_referer(),
            "Origin": cls.origin(),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }

    @classmethod
    def opt_headers(cls):
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Content-Length": "59",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": network_setting.cookie,
            "Host": cls.host,
            "Referer": cls.opt_referer(),
            "Origin": cls.origin(),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }

    @classmethod
    def req_stok_url(cls):
        return f"http://{cls.host}/cgi-bin/luci/;stok=/login?form=login"

    @staticmethod
    def req_stok_data():
        return json.dumps({"method": "login", "params": {"username": USERNAME, "password": PASSWORD}})

    @classmethod
    def req_client_url(cls):
        return f"http://{cls.host}/cgi-bin/luci/;stok={network_setting.stok}/admin/dhcps?form=client"

    @staticmethod
    def req_client_data():
        return json.dumps({"method": "get", "params": {}})

    @classmethod
    def bind_ip_url(cls):
        return f"http://{cls.host}/cgi-bin/luci/;stok={network_setting.stok}/admin/dhcps?form=reservation"

    @classmethod
    def req_static_url(cls):
        # 【static_data】 is same data as 【client_data】
        # Add 【unbind url】 is same url as 【static_url】
        return f"http://{cls.host}/cgi-bin/luci/;stok={network_setting.stok}/admin/dhcps?form=reservation"

    @classmethod
    def get_stok(cls):
        try:
            response = requests.post(cls.req_stok_url(), headers=cls.stok_headers(), data={"data": cls.req_stok_data()})
            json_response = response.json()
            if not VertifyResponse.vertify_stok(json_response):
                logger.error(f"Getted stok Response Error :{str(json_response)}")
                return None
            network_setting.cookie = response.headers.get("Set-Cookie").split(";")[0]
            network_setting.stok = json_response.get("result").get("stok")
            return 0
        except Exception as e:
            logger.error(f"Catch Exception in Get stok {repr(e)} for ip:{cls.host}")
            return None

    @staticmethod
    def vertify_stok_is_available():
        # vertify whether stok and cookie is None
        if network_setting.stok is None or network_setting.cookie is None or Router.client_table() is None:
            ret = Router.get_stok()
            if ret is None:
                return -1
        return 0

    @classmethod
    def client_table(cls):
        client_response = requests.post(cls.req_client_url(), headers=cls.opt_headers(),
                                        data={"data": cls.req_client_data()})

        client_response_json = client_response.json()
        if not VertifyResponse.vertify_client(client_response_json):
            logger.error(f"Getted Error client Response:{client_response_json}")
            return None
        logger.debug(
            f"client_response text:{client_response.text}, client_response status_code:{client_response.status_code} ")

        client_list = client_response_json.get("result")
        return client_list

    @staticmethod
    def spec_ip_info(spec_ip, client_list):
        spec_info = {}
        for i in client_list:
            if spec_ip == i.get("ipaddr"):
                spec_info["leasetime"] = i.get("leasetime")
                spec_info["mac"] = i.get("macaddr")
                spec_info["note"] = i.get("name")
                spec_info["interface"] = i.get("interface").upper()
                spec_info["enable"] = "on"
                spec_info["ip"] = spec_ip
                break
        if spec_info == {}:
            logger.error(f"Info for the specified IP was not found： {spec_ip}")
            return -1
        return spec_info

    @classmethod
    def static_table(cls):
        static_response = requests.post(cls.req_static_url(), headers=cls.opt_headers(),
                                        data={"data": cls.req_client_data()})

        # vertify
        static_response_json = static_response.json()
        if not VertifyResponse.vertify_static(static_response_json):
            logger.error(f"Getted Error StaticList Response:{static_response_json}")
            return None

        logger.debug(
            f"static_response json:{static_response_json}, static_response status_code:{static_response.status_code} ")
        static_list = static_response_json.get("result")
        return static_list

    @staticmethod
    def spec_ip_index(spec_ip, static_list):
        if static_list is None:
            logger.error(f"Getted StaticList is Null.")
            return -1
        ip_index = None
        for index, body in enumerate(static_list):
            if spec_ip == body.get("ip"):
                ip_index = str(index)
                break
        if ip_index is None:
            logger.error("The index value for the specified IP was not found.")
            return -1
        logger.debug(f"Get IP index:{ip_index}")
        return ip_index

    @staticmethod
    def bind_data(spec_ip_info):
        bind_data = {"method": "add", "params": {"index": 0, "old": "add", "new": {}}, "key": "add"}
        bind_data['params']['new']["mac"] = spec_ip_info['mac']
        bind_data['params']['new']["note"] = spec_ip_info['note']
        bind_data['params']['new']["interface"] = spec_ip_info['interface']
        bind_data['params']['new']["enable"] = spec_ip_info['enable']
        bind_data['params']['new']["ip"] = spec_ip_info['ip']
        return bind_data

    @classmethod
    def bind_ip(cls, spec_ip_info):
        if spec_ip_info == -1:
            return -1

        if spec_ip_info["leasetime"] == "Permanent":
            logger.debug(f"The IP: {spec_ip_info['ip']} has already been bound")
            return 0

        bind_ip_data = cls.bind_data(spec_ip_info)
        bind_response = requests.post(url=cls.bind_ip_url(), headers=cls.opt_headers(),
                                      data={"data": json.dumps(bind_ip_data)})
        logger.debug(f"bind response:{bind_response.text} {bind_response.status_code}")
        if not VertifyResponse.vertify_bind(bind_ip_data['params']['new']["mac"], bind_ip_data['params']['new']["note"],
                                            bind_ip_data['params']['new']["ip"], bind_response.json()):
            logger.error(f"Getted Error bind Response:{bind_response.text}")
            return -1
        return 0

    @classmethod
    def unbind_data(cls, wait_to_unbind_ip, static_list):
        wait_to_unbind_ip_index = cls.spec_ip_index(wait_to_unbind_ip, static_list)

        if wait_to_unbind_ip_index == -1:
            return -1

        unbind_data = {"method": "delete",
                       "params": {"key": f"key-{wait_to_unbind_ip_index}", "index": wait_to_unbind_ip_index,
                                  "extraKey": "LAN"}}
        return unbind_data, wait_to_unbind_ip_index

    @classmethod
    def unbind_ip(cls, wait_to_unbind_ip, static_list):
        unbind_data_ret = cls.unbind_data(wait_to_unbind_ip, static_list)
        if unbind_data_ret == -1:
            logger.error("Gettted unbind_data failed.")
            return -1
        unbind_data_info, unbind_ip_index = unbind_data_ret
        unbind_response = requests.post(url=cls.req_static_url(), headers=cls.opt_headers(),
                                        data={"data": json.dumps(unbind_data_info)})

        if not VertifyResponse.vertify_unbind(unbind_ip_index, unbind_response.json()):
            logger.error(f"Getted Error unbind Response:{unbind_response.json()}")
            return -1

        return 0

