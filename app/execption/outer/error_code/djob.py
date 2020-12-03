from app.execption.outer.error import APIException

"""
定义的错误码范围(4000 ~ 4999)
"""


class AssistDeviceOrderError(APIException):
    """
    主机的僚机编号只能是[1，2，3]
    """
    code = 400
    error_code = 4000
    description = 'assist_device order must in [1,2,3]'


class AssistDeviceNotFind(APIException):
    """
    主机没有指定编号的僚机
    """
    code = 400
    error_code = 4001
    description = 'assist_device not find'


class JobMaxRetryCycleException(APIException):
    """
    任务执行循环超过最大次数
    """
    code = 400
    error_code = 4002
    description = 'task execution cycles exceed the maximum number of times'


class InnerJobUnedited(APIException):
    """
    inner job未编辑
    """
    code = 400
    error_code = 4003
    description = 'unedited inner job'


class RemoveJobException(APIException):
    code = 400
    error_code = 4004
    description = 'remove djob exception'


class FloderFailToDeleteException(APIException):
    """
    文件不能被删除的异常
    """
    code = 400
    error_code = 4005
    description = 'floder fail to delete'


class JobExecBodyException(APIException):
    """
    jobbody 解析失败，格式错误
    """
    code = 400
    error_code = 4006
    description = 'Job exec body parse error'


class JobExecUnknownException(APIException):
    """
    任务执行过程中未知错误
    """
    code = 400
    error_code = 4007
    description = 'Job exec unknown exception'
