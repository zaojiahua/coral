import cv2

from app.v1.brain.lib.macBrainTool import macBrain_imgHelpFunc


class DisturbCheck:

    def __init__(self, brain_handle_req_info_obj):
        self.reqInfoObj = brain_handle_req_info_obj
        self.referIm = self.reqInfoObj.getReferImg()
        self.inputIm = self.reqInfoObj.getInputImgFile()
        self.areaDict = self.reqInfoObj.getAreaDict()

    def check(self):
        refer_im = cv2.imread(self.referIm)
        input_im = cv2.imread(self.inputIm)
        if len(self.areaDict) == 0:
            good_match, d = macBrain_imgHelpFunc.surf_a_hist(refer_im, input_im)
            if macBrain_imgHelpFunc.judge(good_match, d):
                return 1
            return 0
        else:
            for k, area in self.areaDict.items():
                good_match, d = macBrain_imgHelpFunc.surf_a_hist(
                    macBrain_imgHelpFunc.get_area(refer_im, area),
                    macBrain_imgHelpFunc.get_area(input_im, area)
                )
                if macBrain_imgHelpFunc.judge(good_match, d): return 1
            return 0
