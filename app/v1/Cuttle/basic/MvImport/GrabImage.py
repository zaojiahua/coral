# -- coding: utf-8 --

import sys
import threading
# import msvcrt
# import glibc
from ctypes import *

sys.path.append("../MvImport")
from .MvCameraControl_class import *

g_bExit = False


# 为线程定义一个函数
def work_thread(cam=0, pData=0, nDataSize=0):
    stFrameInfo = MV_FRAME_OUT_INFO_EX()
    memset(byref(stFrameInfo), 0, sizeof(stFrameInfo))
    while True:
        ret = cam.MV_CC_GetOneFrameTimeout(pData, nDataSize, stFrameInfo, 1000)
        if ret == 0:
            print("get one frame: Width[%d], Height[%d], nFrameNum[%d]" % (
            stFrameInfo.nWidth, stFrameInfo.nHeight, stFrameInfo.nFrameNum))
        else:
            print("no data[0x%x]" % ret)
        if g_bExit == True:
            break

