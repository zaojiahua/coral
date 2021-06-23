from app.config.ip import HOST_IP, REEF_IP
from app.config.setting import CORAL_TYPE
from app.config.url import cabinet_url
from app.libs.http_client import request


def cabinet_register():
    try:
        cabinet_id = HOST_IP.split(".")[-1]

        jsdata = {"cabinet_name": f"I'M {cabinet_id}#-({CORAL_TYPE})",
                  "ip_address": HOST_IP,
                  "is_delete": False,
                  "type": f"Tcab_{CORAL_TYPE}",
                  "id":cabinet_id}
    except:
        cabinet_id = REEF_IP.split(".")[-1]
        jsdata = {"cabinet_name": "default_name"}
    finally:
        res = request(method="POST", json=jsdata, url=cabinet_url + cabinet_id + "/")
        print("---------cabinet register finished-----------")


if __name__ == '__main__':
    cabinet_register()
