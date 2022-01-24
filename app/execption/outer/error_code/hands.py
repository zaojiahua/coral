from app.execption.outer.error import APIException

"""
定义的错误码范围(3000 ~ 3999)
"""


class MethodNotAllow(APIException):
    error_code = 3000
    code = 400
    description = 'hands method is not allow'


class CrossMax(APIException):
    """
    机械臂移动超出范围
    """
    error_code = 3001
    code = 400
    description = 'coordinate over max '


class CoordinateWrongFormat(APIException):
    """
    需要机械臂执行的用例指令非支持的格式
    """
    error_code = 3002
    code = 400
    description = 'coordinate not in correct format '


class KeyPositionUsedBeforesSet(APIException):
    """
    在未设置关键点（返回，菜单，主页，电源，音量）在摄像头位置的情况下，使用到机械臂去点击关键点
    """
    error_code = 3003
    code = 400
    description = 'key point used before used '


class SerialLostConnection(APIException):
    error_code = 3004
    code = 400
    description = 'Arm Serial lost connection'


class SideKeyNotFound(APIException):
    error_code = 3005
    code = 400
    description = 'Press Side Key Not Found'


class ExecContentFormatError(APIException):
    error_code = 3006
    code = 400
    description = 'Exec Content Format Error'
