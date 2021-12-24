from app.execption.outer.error import APIException

"""
定义的错误码范围(8600 ~ 8999)
"""


class ConnectPowerFail(APIException):
    error_code = 8600
    code = 400
    description = '连接继电器失败，请检查继电器状态'



