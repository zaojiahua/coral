from app.execption.outer.error import APIException


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


class CameraInitFail(APIException):
    error_code = 5005
    code = 400
    description = "HK camera init fail"


class ArmReInit(APIException):
    error_code = 5003
    code = 400
    description = "do not send init request twice"


class RemoveBeforeAdd(APIException):
    error_code = 5004
    code = 400
    description = "remove request must after add"
