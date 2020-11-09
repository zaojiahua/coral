from app.config.ip import HOST_IP, REEF_IP
from app.config.url import cabinet_url
from app.libs.http_client import request


def cabinet_register():
    try:
        cabinet_id = HOST_IP.split(".")[-2]

        jsdata = {"cabinet_name": f"I'M {cabinet_id}#",
                  "ip_address": HOST_IP}
    except:
        cabinet_id = REEF_IP.split(".")[-2]
        jsdata = {"cabinet_name": "default_name"}
    finally:
        res = request(method="POST", json=jsdata, url=cabinet_url + cabinet_id + "/")
        print("---------cabinet register finished-----------")

if __name__ == '__main__':
    cabinet_register()
