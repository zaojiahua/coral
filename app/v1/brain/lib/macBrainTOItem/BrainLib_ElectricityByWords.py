from app.v1.brain.lib.macBrainTool import macBrain_getSpecHsvArea

from app.v1.brain.lib import serviceData


class ElectricityByWords:
    def __init__(self, input_img_file, TOItem, brain_handle_req_obj):
        self.inputImgFile = input_img_file
        self.TOItem = TOItem
        self.brainHandleReqObj = brain_handle_req_obj

    def main(self):
        serviceData.logObj.ninfo("begin to match TOItem--ElectricityByWords")
        upper_hsv = [180, 30, 255],
        lower_hsv = [0, 0, 221]
        keywords = ["电量", "充电器", "电池"]
        characters = macBrain_getSpecHsvArea.get_spec_hsv_area(self.inputImgFile, lower_hsv, upper_hsv)
        for key in keywords:
            if key in characters:
                return 0
        return 1
