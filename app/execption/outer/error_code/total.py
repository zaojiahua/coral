from app.execption.outer.error import APIException

"""
定义的错误码范围(600 ~ 998)
"""


class Success(APIException):
    code = 201
    description = 'ok'
    error_code = 600


class DeleteSuccess(Success):
    code = 204
    description = 'delete ok'
    error_code = 601


class ServerError(APIException):
    """
    服务端异常
    """
    code = 500
    description = 'sorry, we made a mistake (*￣︶￣)!'
    error_code = 602


class ClientTypeError(APIException):
    # 400 401 403 404
    # 500
    # 200 201 204
    # 301 302
    code = 400
    description = 'client is invalid'
    error_code = 603


class ParameterException(APIException):
    code = 400
    description = 'invalid parameter'
    error_code = 604


class NotFound(APIException):
    code = 404
    description = 'the resource are not found O__O...'
    error_code = 605


class AuthFailed(APIException):
    code = 401
    error_code = 606
    description = 'authorization failed'


class Forbidden(APIException):
    code = 403
    error_code = 607
    description = 'forbidden, not in scope'


class RequestException(APIException):
    """
    服务内部发送请求异常
    """
    code = 400
    error_code = 608


class RecvHttpException(APIException):
    """
    服务接受请求异常
    """
    code = 400
    error_code = 609
    description = 'server recv request error'
