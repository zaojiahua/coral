from app.config.ip import HOST_IP, REEF_IP
from app.config.setting import CORAL_TYPE, CORAL_TYPE_NAME
from app.config.url import cabinet_url
from app.libs.http_client import request


# 初始化服务时候做的工作
# 将自己的ip，机柜类型上报到数据库
def cabinet_register():
    try:
        cabinet_id = HOST_IP.split(".")[-1]
        jsdata = {"cabinet_name": f"I'M {cabinet_id}#",
                  "ip_address": HOST_IP,
                  "is_delete": False,
                  "type": CORAL_TYPE_NAME[CORAL_TYPE],
                  "id": cabinet_id,
                  }
        if CORAL_TYPE > 4 and CORAL_TYPE not in [5.3, 5.5]:
            m_location = None
            try:
                """
                这里的m_location用于传到reef，展示到前端并对其进行微调
                且Reef和Cedar对柜子类型不敏感
                所以左上角对齐和中心对齐都作为m_location 传出
                """
                from app.config.setting import m_location_center
                m_location = m_location_center
            except ImportError:
                from app.config.setting import m_location
                m_location = m_location
            finally:
                jsdata.update({
                    "m_location_x": m_location[0],
                    "m_location_y": m_location[1],
                    "m_location_z": m_location[2],
                })
    except:
        cabinet_id = REEF_IP.split(".")[-1]
        jsdata = {"cabinet_name": "default_name"}
    finally:
        res = request(method="POST", json=jsdata, url=cabinet_url + cabinet_id + "/")
        print("---------cabinet register finished-----------")


if __name__ == '__main__':
    cabinet_register()
