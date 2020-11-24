from flask import Blueprint

from app.v1.Cuttle.paneDoor.door_view import GetDevice, SetDevice, SetMutiDevice, GetMutiDevice, SetDeviceManual, \
    GetAssisDevice, SetAssisDevice, OpenPort

door = Blueprint('door', __name__)


# TEST EXAMPLE FOR STEW
request_body = {"temperature_port_list": ["TA-01"],
                "auto_recommend": True,
                "device_label": "cactus---mt6765---ce3c9b227d2a",
                "device_ipAddress": "10.80.3.26",
                "phone_module": "cactus",
                "android_version": "9",
                "id": 17}
#todo 内部逻辑重复，且已经开始混乱，有时间的时候需要对此模块进行整体重构
#TODo 重构时需要考虑此模块分离出物理设备的可能性
door.add_url_rule('/set_device_in_door/', view_func=SetDevice.as_view('set_device_in_door'))
door.add_url_rule('/get_device_in_door/', view_func=GetDevice.as_view('get_device_in_door'))
door.add_url_rule('/get_assistance_device_in_door/', view_func=GetAssisDevice.as_view('get_assistance_device_in_door'))
door.add_url_rule('/set_assistance_device_in_door/', view_func=SetAssisDevice.as_view('set_assistance_device_in_door'))
door.add_url_rule('/manual_registration/', view_func=SetDeviceManual.as_view('manual_registration'))
door.add_url_rule('/get_muti-device_in_door/', view_func=GetMutiDevice.as_view('get_muti_device_in_door'))
door.add_url_rule('/set_muti-device_in_door/', view_func=SetMutiDevice.as_view('set_muti_device_in_door'))
door.add_url_rule('/wifi_port/', view_func=OpenPort.as_view('wifi_port'))
