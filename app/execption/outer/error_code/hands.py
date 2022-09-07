from app.execption.outer.error import APIException

"""
定义的错误码范围(3000 ~ 3999)
"""


class MethodNotAllow(APIException):
    error_code = 3000
    code = 400
    description = 'hands method is not allow'


class CrossMax(APIException):
    """
    机械臂移动超出范围
    """
    error_code = 3001
    code = 400
    description = 'coordinate over max '


class CoordinateWrongFormat(APIException):
    """
    需要机械臂执行的用例指令非支持的格式
    """
    error_code = 3002
    code = 400
    description = 'coordinate not in correct format '


class KeyPositionUsedBeforesSet(APIException):
    """
    在未设置关键点（返回，菜单，主页，电源，音量）在摄像头位置的情况下，使用到机械臂去点击关键点
    """
    error_code = 3003
    code = 400
    description = 'key point used before used '


class SerialLostConnection(APIException):
    """
    与机械臂失去连接
    """
    error_code = 3004
    code = 400
    description = 'Arm Serial lost connection'


class SideKeyNotFound(APIException):
    """
    未在设备地图中添加侧边键坐标值
    """
    error_code = 3005
    code = 400
    description = 'Press Side Key Not Found'


class ExecContentFormatError(APIException):
    error_code = 3006
    code = 400
    description = 'Exec Content Format Error'


class CoordinatesNotReasonable(APIException):
    """
    侧边键坐标应在屏幕外
    """
    error_code = 3007
    code = 400
    description = 'The Side Key Coordinates Should Not be In the Screen'


class ControlUSBPowerFail(APIException):
    """
    控制USB通断模块失败
    """
    error_code = 3008
    code = 400
    description = 'Control USB Power Fail'


class ChooseSerialObjFail(APIException):
    """
    未知的机械臂执行对象
    """
    error_code = 3009
    code = 400
    description = 'Unknown Execution G code Serial object '


class InvalidCoordinates(APIException):
    """
     当使用双指缩小与放大unit时，必须满足：
        4个点的x坐标均需保持安全距离且两条线段不能相交、
    当使用回到桌面（全面屏）时，需|起点坐标|大于|终点坐标|
    """
    error_code = 3010
    code = 400
    description = "Invalid Coordinates "


class RepeatTimeInvalid(APIException):
    """
    重复次数超过限制
    """
    error_code = 3012
    code = 400
    description = "Repeat Time Out of Range 1-10"


class TcabNotAllowExecThisUnit(APIException):
    """
    目前该Tcab柜子类型不支持这个unit的执行
    """
    error_code = 3013
    code = 400
    description = "This Tcab Type Not Allow Exec This Unit"


class UsingHandFail(APIException):
    """
    机械臂正在使用中，无法下发新指令
    """
    error_code = 3013
    code = 400
    description = "机械臂正在使用中，请稍后重试！"
