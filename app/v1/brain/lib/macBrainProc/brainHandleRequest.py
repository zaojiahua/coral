from app.v1.brain.lib.macBrainTool import macBrain_imgHelpFunc


class BrainHandleRequest:

    def __init__(self, refer_img, refer_img_area, dut_dict, input_img_file, text_list):
        self.referImg = refer_img
        self.referImgArea = refer_img_area
        self.devInfo = dut_dict
        self.inputImgFile = input_img_file
        self.TextList = text_list

    def get_device_id(self):
        return self.devInfo["deviceID"]

    def get_input_img_file(self):
        return self.inputImgFile

    def get_text_list(self):
        return self.TextList

    def get_dut_dict(self):
        return self.devInfo

    def get_djob_work(self):
        return self.devInfo["datPathDict"]["djobwork"]

    def get_dev_prod_name(self):
        return self.devInfo["productName"]

    def get_refer_img(self):
        return self.referImg

    def get_area_dict(self):
        # areaDict = macBrain_imgHelpFunc.readReferInfo(self.referInfo)
        # if len(areaDict) == 0:
        #     return {}
        # else:
        #     return areaDict
        if self.referImgArea is None:
            return {}
        return self.referImgArea

    def get_refer_info(self):
        pass
