from app.execption.outer.error import APIException

"""
定义的错误码范围(6000 ~ 6999)
"""


class GetResourceFail(APIException):
    code = 417
    error_code = 6000
