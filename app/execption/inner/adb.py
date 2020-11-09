from app.execption.outer.error import APIException


class AdbConnectFail(Exception):
    error_code = -3
    description = "device wifi not connect / or some other progress is connecting this device"


class AdbRootFail(Exception):
    error_code = -4
    description = "device do not have root authority"


class AdbException(Exception):
    description = "for device re-connect"


class UnknowHandler(APIException):
    error_code = 1011
    code = 400
    description = 'UnknowHandler '
