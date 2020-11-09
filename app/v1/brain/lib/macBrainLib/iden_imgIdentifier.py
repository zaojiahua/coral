from app.v1.brain.lib.macBrainLib import iden_imgCompareThread, iden_imgIdenResult


class Iden_imgIdentifier:
    def __init__(self, input_img, TOItem_list, brain_handle_req_obj):
        self.inputImg = input_img
        self.TOItemList = TOItem_list
        self.brainHandleReqObj = brain_handle_req_obj

    def img_identifier_mgr(self):
        TOItem_match_res = {}  # {"TOItem-UUID":0, "TOItem-UUID":1....}
        TOItem_match_thrd = {}
        for TOItem in self.TOItemList:
            TOItem_match_thrd[TOItem] = iden_imgCompareThread.Iden_imgCompareThread(self.inputImg, TOItem,
                                                                                    self.brainHandleReqObj)
            TOItem_match_thrd[TOItem].start()

        for TOItem in self.TOItemList:
            TOItem_match_thrd[TOItem].join()

        for TOItem in self.TOItemList:
            TOItem_match_res[TOItem] = TOItem_match_thrd[TOItem].get_result()
        return iden_imgIdenResult.iden_imgIdenResult(TOItem_match_res)
