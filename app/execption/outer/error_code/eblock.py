from app.execption.outer.error import APIException

"""
定义的错误码范围(7000 ~ 7999)
"""


class EblockEarlyStop(APIException):
    error_code = 7001
    code = 400
    description = 'eblock is asked for stop while doing a block'


class EblockCannotFindFile(APIException):
    error_code = 7002
    code = 400
    description = 'eblock can not find a input file'


class EblockTimeOut(APIException):
    """
    unit执行时间超过最大限制
    """
    error_code = 7003
    code = 400
    description = 'eblock time out'


class MaroUnrecognition(APIException):
    error_code = 7004
    code = 400
    description = 'find unknow Maro'

class EblockResourceMacroWrongFormat(APIException):
    error_code = 7005
    code = 400
    description = 'eblock find wrong type of resource macro'

class DeviceNeedResource(APIException):
    error_code = 7006
    code = 400
    description = 'use resource before assign to device or input wrong'
