from app.v1.brain.lib import serviceData


class Electricity(object):
    def __init__(self, input_img_file, TOItem, brain_handle_req_obj):
        self.inputImgFile = input_img_file
        self.TOItem = TOItem
        self.brainHandleReqObj = brain_handle_req_obj

    def main(self):
        serviceData.logObj.ninfo("begin to match TOItem--Electricity")
        return 1
