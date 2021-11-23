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
    主设备没有相应僚机编号的僚机设备
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


class JobFlowNotFound(APIException):
    """
    任务执行的罗辑流程图缺失
    """
    code = 400
    error_code = 4008
    description = 'job flow not found'


class InnerJobNotAssociated(APIException):
    """
    inner job 虽然在流程图里有指明，但是并未真正关联。
    执行时没有inner job，执行失败。建议打开job重新保存。
    """
    code = 400
    error_code = 4009
    description = 'inner job not associated'


class ImageIsNoneException(APIException):
    """
    图片为空，可能原因是要测试的软件不允许截图，请检查
    """
    code = 400
    error_code = 4010
    description = 'image is none exception'
