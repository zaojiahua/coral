from app.execption.outer.error import APIException


class EblockEarlyStop(APIException):
    error_code = -20
    code = 400
    description = 'eblock is asked for stop while doing a block'


class EblockCannotFindFile(APIException):
    error_code = -19
    code = 400
    description = 'eblock can not find a input file'


class EblockTimeOut(APIException):
    """
    unit执行时间超过最大限制
    """
    error_code = -17
    code = 400
    description = 'eblock time out'


class MaroUnrecognition(APIException):
    error_code = -16
    code = 400
    description = 'find unknow Maro'
