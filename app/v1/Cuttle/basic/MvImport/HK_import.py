import platform

from app.config.setting import CORAL_TYPE
from app.v1.Cuttle.basic.setting import g_bExit

if CORAL_TYPE == 5:
    if platform.system() == 'Linux':
        pass
        # REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_IP}:6379/0"
    else:
        from app.v1.Cuttle.basic.MvImport.windows.CameraParams_const import MV_USB_DEVICE, MV_GIGE_DEVICE
        from app.v1.Cuttle.basic.MvImport.windows.CameraParams_header import MV_CC_DEVICE_INFO_LIST, MVCC_INTVALUE, \
            MV_FRAME_OUT_INFO_EX, MV_CC_DEVICE_INFO, MV_SAVE_IMAGE_PARAM_EX, MV_Image_Jpeg
        from app.v1.Cuttle.basic.MvImport.windows.MvCameraControl_class import MvCamera