from app.execption.outer.error import APIException

"""
定义的错误码范围(5000 ~ 5999)
"""


class NoSrc(APIException):
    """
    摄像头在执行拉取图片指令前缺少截图命令
    """
    error_code = 5000
    code = 400
    description = "pull picture must after snap-shot"


class NoArm(APIException):
    error_code = 5001
    code = 400
    description = "arm id not found"


class NoCamera(APIException):
    error_code = 5002
    code = 400
    description = "camera id not found"


class ArmReInit(APIException):
    error_code = 5003
    code = 400
    description = "do not send init request twice"


class RemoveBeforeAdd(APIException):
    error_code = 5004
    code = 400
    description = "remove request must after add"


class CameraInitFail(APIException):
    error_code = 5005
    code = 400
    description = "HK camera init fail"


class PerformancePicNotFound(APIException):
    error_code = 5006
    code = 400
    description = "performance picture path not found "


class CameraInUse(APIException):
    error_code = 5007
    code = 400
    description = "相机正在使用中，请稍后重试。"
