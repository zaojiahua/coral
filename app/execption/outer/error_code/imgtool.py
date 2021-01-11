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
    ocr图片路径下没有图片
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


class VideoKeyPointNotFound(APIException):
    """
    视频处理过程中，没有发现预定帧
    """
    error_code = 2008
    code = 400
    description = "can not key point in video"


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
    error_code = 2014
    code = 400
    description = "color position exceed max border"

