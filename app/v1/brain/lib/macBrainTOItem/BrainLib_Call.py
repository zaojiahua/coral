import os

from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainTool import macBrain_compareForCall


class Call:
    def __init__(self, input_im, TOItemID, brain_handle_req_obj):
        self.inputIm = input_im
        self.TOItemID = TOItemID
        self.brainHandleReqObj = brain_handle_req_obj

    def main(self):
        serviceData.logObj.ninfo("begin to match TOItem--Call")
        TOItem_img_info = serviceData.TOItemInfoObj[self.TOItemID].getImgMatch()
        TOItem_img = os.path.join(serviceData.brainLibPath, self.TOItemID, list(TOItem_img_info.keys())[0])
        result = macBrain_compareForCall.main(self.inputIm, TOItem_img)
        if result != 1:
            click_point = result
            swipe_point = [result[0], result[1], result[0], (result[1] - 200)]
            self.write_click_point(click_point)
            self.write_swipe_point(swipe_point)
            return 0
        return 1

    def write_click_point(self, click_point):
        f = open(os.path.join(self.brainHandleReqObj.getDjobWork(), "tap1position.txt"), 'w')
        l = [str(click_point[0]), " ", str(click_point[1])]
        f.writelines(l)
        f.close()
        return 0

    def write_swipe_point(self, swipe_point):
        f = open(os.path.join(self.brainHandleReqObj.getDjobWork(), "swap1position.txt"), 'w')
        l = [str(swipe_point[0]), " ", str(swipe_point[1]), " ", str(swipe_point[2]), " ", str(swipe_point[3])]
        f.writelines(l)
        f.close()
        return 0
