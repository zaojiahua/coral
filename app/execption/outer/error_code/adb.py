from app.execption.outer.error import APIException

"""
定义的错误码范围(1000 ~ 1999)
"""


class NoMoreThanOneDevice(APIException):
    error_code = 1000
    code = 400
    description = '注册设备时，主机上只能连接一台未注册的设备。'


class DeviceNotInUsb(APIException):
    error_code = 1001
    code = 400
    description = "无法连接设备。请检查设备是否连接注册线、USB调试是否打开。"


class DeviceChanged(APIException):
    error_code = 1002
    code = 400
    description = "usb-device changed during registration "


class DeviceCannotSetprop(APIException):
    error_code = 1003
    code = 400
    description = "can not open 5555 port in devcie"


class DeviceRegisterInterrupt(APIException):
    error_code = 1004
    code = 400
    description = "part of device finished registration, others fail"


class DeviceBindFail(APIException):
    error_code = 1005
    code = 400
    description = "bind/unbind device ip address in router fail"


class DeviceWmSizeFail(APIException):
    error_code = 1006
    code = 400
    description = "do you connect a phone which is shut down?"


class DeviceAlreadyInCabinet(APIException):
    error_code = 1007
    code = 400
    description = "设备已存在于当前系统中，请检查。"


class UnitBusy(APIException):
    """
    adb指令长时间无响应，adb busy
    """
    error_code = 1008
    code = 400
    description = "AdbBusy"


class NoContent(APIException):
    """
    需要执行的adb语句没有内容
    """
    error_code = 1009
    code = 400
    description = "unit cmd no content"


class PinyinTransferFail(APIException):
    """
    无法识别的拼音字母
    """
    error_code = 1010
    code = 400
    description = "un-recognize pinyin"


class ArmNorEnough(APIException):
    """
    一个机柜同时只能存在一个可用设备，需要先注销已有设备，再进行注册
    """
    error_code = 1011
    code = 400
    description = "添加失败！该机柜中已有1台设备，请先将其移除。"


class FindAppVersionFail(APIException):
    """
    获取APP版本失败，可能原因是手机没有安装此APP或者ADB连接断开
    """
    error_code = 1012
    code = 400
    description = "获取APP版本失败，可能原因是手机没有安装此APP或者ADB连接断开"


# 之前定义了一些错误码，迁移过来，范围不是1000多，兼容之前的
class AdbConnectFail(APIException):
    error_code = -3
    description = "device not found，多见设备没连/连错wifi"
