import threading

from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainTOItem import BrainLib_Call, BrainLib_ElectricityByWords, BrianLib_Electricity, \
    BrainLib_Call4RedMi, BrainLib_identifyRedArea4Elec


class Iden_imgCompareThread(threading.Thread):
    def __init__(self, input_img_file, TOItem, brain_handle_req_obj):
        threading.Thread.__init__(self)
        self.inputImgFile = input_img_file
        self.TOItem = TOItem
        self.brainHandleReqObj = brain_handle_req_obj
        self.returnRes = 1  # 0|1

    def run(self):
        TOItem_name = serviceData.TOItemInfoObj[self.TOItem].getTOItemName()
        if TOItem_name == 'Call':
            call_obj = BrainLib_Call.Call(self.inputImgFile, self.TOItem, self.brainHandleReqObj)
            self.returnRes = call_obj.main()
        elif TOItem_name == 'ElectricityByWords':
            elc_by_words = BrainLib_ElectricityByWords.ElectricityByWords(self.inputImgFile, self.TOItem,
                                                                          self.brainHandleReqObj)
            self.returnRes = elc_by_words.main()
        elif TOItem_name == 'Electricity':
            elc = BrianLib_Electricity.Electricity(self.inputImgFile, self.TOItem, self.brainHandleReqObj)
            self.returnRes = elc.main()
        elif TOItem_name == 'Call4RedMi':
            call_4_redmi = BrainLib_Call4RedMi.Call4RedMi(self.inputImgFile, self.TOItem, self.brainHandleReqObj)
            self.returnRes = call_4_redmi.main()
        elif TOItem_name == 'ElectricityByRed':
            red_rlec = BrainLib_identifyRedArea4Elec.IdentifyRedArea4Elec(self.inputImgFile, self.TOItem,
                                                                          self.brainHandleReqObj)
            self.returnRes = red_rlec.main()
        else:
            pass
        return self.returnRes

    def get_result(self):
        return self.returnRes
