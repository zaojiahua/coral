import platform
import math

from app.config.setting import CORAL_TYPE

if math.floor(CORAL_TYPE) == 5:
    if platform.system() == 'Linux':
        from app.v1.Cuttle.basic.MvImport.linux.CameraParams_const import MV_USB_DEVICE, MV_GIGE_DEVICE
        from app.v1.Cuttle.basic.MvImport.linux.CameraParams_header import MV_CC_DEVICE_INFO_LIST, MVCC_INTVALUE, \
            MV_FRAME_OUT_INFO_EX, MV_CC_DEVICE_INFO, MV_SAVE_IMAGE_PARAM_EX, MV_Image_Jpeg, MVCC_FLOATVALUE
        from app.v1.Cuttle.basic.MvImport.linux.MvCameraControl_class import MvCamera
        from app.v1.Cuttle.basic.MvImport.linux.CameraParams_header import MV_CC_PIXEL_CONVERT_PARAM
        from app.v1.Cuttle.basic.MvImport.linux.PixelType_header import PixelType_Gvsp_BGR8_Packed
    else:
        from app.v1.Cuttle.basic.MvImport.windows.CameraParams_const import MV_USB_DEVICE, MV_GIGE_DEVICE
        from app.v1.Cuttle.basic.MvImport.windows.CameraParams_header import MV_CC_DEVICE_INFO_LIST, MVCC_INTVALUE, \
            MV_FRAME_OUT_INFO_EX, MV_CC_DEVICE_INFO, MV_SAVE_IMAGE_PARAM_EX, MV_Image_Jpeg,MV_FRAME_OUT_INFO_EX, MVCC_FLOATVALUE
        from app.v1.Cuttle.basic.MvImport.windows.MvCameraControl_class import MvCamera
        from app.v1.Cuttle.basic.MvImport.windows.CameraParams_header import MV_CC_PIXEL_CONVERT_PARAM
        from app.v1.Cuttle.basic.MvImport.windows.PixelType_header import PixelType_Gvsp_BGR8_Packed