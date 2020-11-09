from app.execption.outer.error import APIException


class MethodNotAllow(APIException):
    error_code = 4001
    code = 400
    description = 'hands method is not allow'


class CrossMax(APIException):
    """
    机械臂移动超出范围
    """
    error_code = 4002
    code = 400
    description = 'coordinate over max '


class CoordinateWrongFormat(APIException):
    """
    需要机械臂执行的用例指令非支持的格式
    """
    error_code = 4003
    code = 400
    description = 'coordinate not in correct format '
