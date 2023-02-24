from app.execption.outer.error import APIException

"""
定义的错误码范围(11000 ~ 11999)
"""


class ActionNotAllow(APIException):
    """
    不支持的夹爪动作
    """
    error_code = 11000
    code = 400
    description = 'jaw method is not allow'

