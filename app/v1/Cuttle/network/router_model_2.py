import json

import requests

from app.v1.Cuttle.network import network_setting
from app.v1.Cuttle.network.network_setting import USERNAME, NEWPASS, logger, ROUTER_IP


class NewRouter:
    host = ROUTER_IP
    origin = f"http://{host}"
    referer = f"http://{host}/login.htm"
    headers = {
        "Accept": "text/plain, */*; q=0.01",
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Content-Length': '77',
        'Content-Type': 'application/json; charset=UTF-8',
        'Host': host,
        'Origin': origin,
        'Proxy-Connection': 'keep-alive',
        'Referer': referer,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }

    def __init__(self):
        pass

    @classmethod
    def req_stok_url(cls):
        return f"http://{cls.host}/"

    @staticmethod
    def req_stok_data():
        return json.dumps({
            "method": "do",
            "login": {
                "username": USERNAME,
                "password": NEWPASS
            }
        })

    @classmethod
    def req_url(cls):
        return f"http://{cls.host}/stok={network_setting.new_stok}/ds"

    @staticmethod
    def req_client_data():
        return json.dumps({"method": "get",
                           "global_config": {
                               "name": "page_size"
                           },
                           "dhcpd": {
                               "table": "dhcp_clients",
                               "para": {
                                   "start": "0",
                                   "end": "500"
                               }
                           }
                           })

    @staticmethod
    def req_static_data():
        return json.dumps({"method": "get",
                           "dhcpd": {
                               "table": "dhcp_static",
                               "para": {
                                   "start": 0,
                                   "end": 199
                               }
                           }
                           })

    @staticmethod
    def bind_data(mac, ip):
        return json.dumps({"method": "add",
                           "dhcpd": {
                               "table": "dhcp_static",
                               "para": {
                                   "mac": mac,
                                   "ip": ip,
                                   "note": "",
                                   "enable": "on"
                               }
                           }
                           })

    @staticmethod
    def unbind_data(static_index_id):
        return json.dumps({"method": "delete",
                           "dhcpd": {
                               "table": "dhcp_static",
                               "filter": [
                                   {
                                       "dhcp_static_id": static_index_id
                                   }
                               ]
                           }
                           })

    @classmethod
    def get_stok(cls):
        try:
            response = requests.post(cls.req_stok_url(),
                                     headers=cls.headers,
                                     data=cls.req_stok_data())
            json_response = response.json()
            if json_response.get("error_code") != 0:
                logger.error(f"Getted stok Response Error :{str(json_response)}")
                return None
            network_setting.new_stok = json_response.get("stok")
            return 0
        except Exception as e:
            logger.error(f"Catch Exception in Get stok {repr(e)} for ip:{cls.host}")
            return None

    @classmethod
    def vertify_stok_is_available(cls):
        # vertify whether stok and cookie is None
        if network_setting.new_stok is None or cls.client_table() is None:
            ret = cls.get_stok()
            if ret is None:
                return -1
        return 0

    @classmethod
    def client_table(cls):
        client_response = requests.post(cls.req_url(),
                                        headers=cls.headers,
                                        data=cls.req_client_data())
        client_response_json = client_response.json()
        if client_response_json.get("error_code") != 0:
            logger.error(f"Getted Error client Response:{client_response_json}")
            return None
        logger.debug(
            f"client_response text:{client_response.text}, client_response status_code:{client_response.status_code} ")

        # client_list: List
        client_list = client_response_json.get("dhcpd").get("dhcp_clients")
        return client_list

    @staticmethod
    def spec_ip_mac(spec_ip, client_list):
        ip_info = {}
        # i : Dict
        for i in client_list:
            # client_info : Str
            for client_info in i:
                if i[client_info]["ipaddr"] == spec_ip:
                    ip_mac = i[client_info].get("macaddr")
                    ip_expires = i[client_info].get("expires")
                    ip_info["ip_mac"] = ip_mac
                    ip_info["ip_expires"] = ip_expires
                    break
        if ip_info == {}:
            logger.error(f"Info for the specified IP was not found： {spec_ip}")
            return -1
        return ip_info

    @classmethod
    def static_table(cls):
        static_response = requests.post(cls.req_url(),
                                        headers=cls.headers,
                                        data=cls.req_static_data())

        static_response_json = static_response.json()
        if static_response_json.get('error_code') != 0:
            logger.error(f"Getted Error StaticList Response:{static_response_json}")
            return None

        logger.debug(
            f"static_response json:{static_response_json}, static_response status_code:{static_response.status_code} ")
        static_list = static_response_json['dhcpd']['dhcp_static']
        return static_list

    @staticmethod
    def spec_ip_index(spec_ip, static_list):
        if static_list is None:
            logger.error(f"Getted StaticList is Null.")
            return -1
        ip_index = None
        for i in static_list:
            for info in i:
                if i[info]['ip'] == spec_ip:
                    ip_index = i[info].get("dhcp_static_id")
                    break
        if ip_index is None:
            logger.error("The index value for the specified IP was not found.")
            return 2
        logger.debug(f"Get IP index:{ip_index}")
        return ip_index

    @classmethod
    def bind_ip(cls, ip):
        client_list = cls.client_table()
        # 获取设备mac地址
        ip_info = cls.spec_ip_mac(ip, client_list)
        if ip_info == -1:
            logger.error(f"Getted MACaddr failed.")
            return -1
        if ip_info['ip_expires'] == "PERMANENT":
            return 0
        bind_data = cls.bind_data(ip_info['ip_mac'], ip)
        bind_response = requests.post(url=cls.req_url(),
                                      headers=cls.headers,
                                      data=bind_data)

        logger.debug(f"bind response:{bind_response.text} {bind_response.status_code}")
        bind_response_json = bind_response.json()
        if bind_response_json.get("error_code") != 0:
            logger.error(f"Getted Error bind Response:{bind_response.text}")
            return -1
        return 0

    @classmethod
    def unbind_ip(cls, wait_to_unbind_ip):
        static_list = cls.static_table()
        # 获取ip_index
        ip_index = cls.spec_ip_index(wait_to_unbind_ip, static_list)
        if ip_index == -1:
            logger.error("Gettted unbind_data failed.")
            return -1
        elif ip_index == 2:
            return 0
        unbind_data = cls.unbind_data(ip_index)
        unbind_response = requests.post(url=cls.req_url(),
                                        headers=cls.headers,
                                        data=unbind_data)
        unbind_response_json = unbind_response.json()
        if unbind_response_json.get("error_code") != 0:
            logger.error(f"Getted Error unbind Response:{unbind_response.json()}")
            return -1

        return 0


if __name__ == '__main__':
    NewRouter.get_stok()
    print(NewRouter.client_table())
    # ret = NewRouter.bind_ip("10.81.3.5")
    # ret = NewRouter.unbind_ip("10.81.3.3")
    # print(ret)
