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
