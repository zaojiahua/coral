import os

import cv2
from ServCent import serviceData
from macBrainTool import macBrain_imgHelpFunc


class Call4RedMi(object):
    def __init__(self, inputIm, TOItemID, brainHandleReqObj):
        self.inputIm = inputIm
        self.TOItemID = TOItemID
        self.brainHandleReqObj = brainHandleReqObj

    def main(self):
        serviceData.logObj.ninfo("begin to match TOItem--Call4RedMi")
        if self.compare() != 1:
            self.writeClickPoint()
            self.writeSwipePoint()
            return 0
        return 1

    def compare(self):
        TOItemImgInfo = serviceData.TOItemInfoObj[self.TOItemID].getImgMatch()
        TOItemImg = os.path.join(serviceData.brainLibPath, self.TOItemID, list(TOItemImgInfo.keys())[0])
        referIm = cv2.imread(TOItemImg)
        inputIm = cv2.imread(self.inputIm)
        imgH, imgW = inputIm.shape[:2]
        im = inputIm[690:imgH, 0:imgW]
        goodMatch, d = macBrain_imgHelpFunc.surfAhist(referIm, im)
        if macBrain_imgHelpFunc.judge(goodMatch, d): return 1
        return 0

    def writeClickPoint(self):
        f = open(os.path.join(self.brainHandleReqObj.getDjobWork(), "tap1position.txt"), 'w')
        l = ["358", " ", "1039"]
        f.writelines(l)
        f.close()
        serviceData.logObj.ninfo("call4RedMi write tap1position.txt is ok!")
        return 0

    def writeSwipePoint(self):
        f = open(os.path.join(self.brainHandleReqObj.getDjobWork(), "swap1position.txt"), 'w')
        l = ["358", " ", "1039", " ", "0", " ", "1039"]
        f.writelines(l)
        f.close()
        serviceData.logObj.ninfo("call4RedMi write swap1position.txt is ok!")
        return 0
