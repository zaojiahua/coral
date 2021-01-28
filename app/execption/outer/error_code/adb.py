from app.execption.outer.error import APIException

"""
定义的错误码范围(1000 ~ 1999)
"""


class NoMoreThanOneDevice(APIException):
    error_code = 1000
    code = 400
    description = 'single device register only allow one device in usb'


class DeviceNotInUsb(APIException):
    error_code = 1001
    code = 400
    description = "DO YOU FORGET CONNECT DEVICE? or Your device already in other cabinet"


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
    description = "need to logout device in this or other cabinet first"


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
