from flask import Blueprint

from app.v1.Cuttle.paneDoor.door_view import GetDevice, SetDevice, SetMutiDevice, GetMutiDevice, SetDeviceManual, \
    GetAssisDevice, SetAssisDevice, OpenPort, UpdateDeviceInfo

door = Blueprint('door', __name__)

# todo 内部逻辑重复，且已经开始混乱，有时间的时候需要对此模块进行整体重构
# TODo 重构时需要考虑此模块分离出物理设备的可能性

# 前两个为设备注册用url，先get 再set
door.add_url_rule('/set_device_in_door/', view_func=SetDevice.as_view('set_device_in_door'))
door.add_url_rule('/get_device_in_door/', view_func=GetDevice.as_view('get_device_in_door'))
# 注册僚机的url，顺序同主机先get 再set
door.add_url_rule('/get_assistance_device_in_door/', view_func=GetAssisDevice.as_view('get_assistance_device_in_door'))
door.add_url_rule('/set_assistance_device_in_door/', view_func=SetAssisDevice.as_view('set_assistance_device_in_door'))
# 注册非adb设备的url
door.add_url_rule('/manual_registration/', view_func=SetDeviceManual.as_view('manual_registration'))
# 批量注册设备的url（未启用）
door.add_url_rule('/get_muti-device_in_door/', view_func=GetMutiDevice.as_view('get_muti_device_in_door'))
door.add_url_rule('/set_muti-device_in_door/', view_func=SetMutiDevice.as_view('set_muti_device_in_door'))
# 重新连接功能的url
door.add_url_rule('/wifi_port/', view_func=OpenPort.as_view('wifi_port'))
# 更新设备信息的url
door.add_url_rule('/device_info/', view_func=UpdateDeviceInfo.as_view('device_info'))
