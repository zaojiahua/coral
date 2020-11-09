from app.execption.outer.error import APIException


class GetResourceFail(APIException):
    code = 417
    error_code = 3000
