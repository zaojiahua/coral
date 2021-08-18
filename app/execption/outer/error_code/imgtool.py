from app.execption.outer.error import APIException

"""
定义的错误码范围(2000 ~ 2999)
"""


class OcrRetryTooManyTimes(APIException):
    """
    ocr服务没有响应
    """
    error_code = 2001
    code = 400
    description = "orc retry over 3 times"


class OcrParseFail(APIException):
    error_code = 2002
    code = 400
    description = "no required word in ocr's result"


class OcrWorkPathNotFound(APIException):
    """
    ocr图片路径下没有图片，可能原因是设备存储空间已满。
    """
    error_code = 2003
    code = 400
    description = "orc can not found work path"


class ComplexSnapShotFail(APIException):
    """
    复合unit内，截图失败
    """
    error_code = 2004
    code = 400
    description = "snap shot for getting  complex  refer image fail"


class ClearBouncedOK(APIException):
    """
    T-gard处理干扰(已知弹窗),多(3)次处理后未解决
    """
    error_code = 2005
    code = 400
    description = "the Bounced is cleared"


class NotFindBouncedWords(APIException):
    error_code = 2006
    code = 400
    description = "compared error but not find any Bounced Words"


class NotFindIcon(APIException):
    error_code = 2007
    code = 400
    description = "can not find icon"


class VideoStartPointNotFound(APIException):
    """
    性能分析过程中，没有找到起始标志点
    """
    error_code = 2008
    code = 400
    description = "can not find start point in video"


class OcrShiftWrongFormat(APIException):
    """
    复合unit内，偏移量格式错误，多见与多一个空格或写成小数
    """
    error_code = 2009
    code = 400
    description = "orc shift get wrong format"


class IconTooWeek(APIException):
    """
    复合unit内，选区的图标特征过弱，特征点小于4个
    """
    error_code = 2010
    code = 400
    description = "icon is too week so that surf cannot find any descriptor"


class EndPointWrongFormat(APIException):
    """
    复合unit内，偏移量格式错误，多见与多一个空格或写成小数
    """
    error_code = 2011
    code = 400
    description = "press and swipe end point get wrong format"

class SwipeAndFindWordsFail(APIException):
    error_code = 2012
    code = 400
    description = "can not find required words until swipe to the end"

class ColorPositionCrossMax(APIException):
    error_code = 2013
    code = 400
    description = "color position exceed max border"

class RecordWordsFindNoWords(APIException):
    """
    文字记录unit 不能在截图的选区中发现任何文字
    """
    error_code = 2014
    code = 400
    description = "record-words unit can not find any words in crop-picture"

class CannotFindRecentVideoOrImage(APIException):
    error_code = 2015
    code = 400
    description = "can not find recent video or Imgae in 300s"

class WrongEndPoint(APIException):
    """
    性能测试中，终止点识别错误，提前误识别出结果
    """
    error_code = 2016
    code = 400
    description = "find wrong end point in performance"

class VideoEndPointNotFound(APIException):
    """
    性能测试中，没有发现结束帧
    """
    error_code = 2017
    code = 400
    description = "can not find end point in video"

class FpsLostWrongValue(APIException):
    error_code = 2018
    code = 400
    description = "fps lost only support 60 90 120"

