from app.execption.outer.error import APIException


class JobExecBodyException(APIException):
    """
    jobbody 解析失败，格式错误
    """
    code = 400
    error_code = 4006
    description = 'Job exec body parse error'


class JobExecUnknownException(APIException):
    """
    执行过程中未知错误
    """
    code = 400
    error_code = 4007
    description = 'Job exec unknown exception'


class RemoveJobException(APIException):
    code = 400
    error_code = 4008
    description = 'remove djob exception'


class FloderFailToDeleteException(APIException):
    """
    文件不能被删除的异常
    """
    code = 400
    error_code = 4009
    description = 'floder fail to delete'


class AssistDeviceOrderError(APIException):
    """
    主机的僚机编号只能是[1，2，3]
    """
    code = 400
    error_code = 4010
    description = 'assist_device order must in [1,2,3]'


class AssistDeviceNotFind(APIException):
    """
    主机没有指定编号的僚机
    """
    code = 400
    error_code = 4011
    description = 'assist_device not find'


class JobMaxRetryCycleException(APIException):
    """
    任务执行循环超过最大次数
    """
    code = 400
    error_code = 4012
    description = 'task execution cycles exceed the maximum number of times'


class InnerJobUnedited(APIException):
    """
    inner job未编辑
    """
    code = 400
    error_code = 4013
    description = 'unedited inner job'
