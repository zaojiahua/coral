import threading

from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainLib import iden_identifierMgr, dec_decisionMakerMgr, op_operatorMgr
from app.v1.brain.lib.macBrainTool import macBrain_callbackToDjob


class BrainHandleThread(threading.Thread):

    def __init__(self, brain_handle_req_obj):
        threading.Thread.__init__(self)
        self.brainHandleReqObj = brain_handle_req_obj
        self.handleExceRet = 1
        self.handleExceStateFlag = 1

    def run(self):
        """
        Djob只关心能否往下进行，故只需要返回 yes or no
        """
        dev_id = self.brainHandleReqObj.getDeviceID()
        iden_ret_set = iden_identifierMgr.iden_identifierMgr(self.brainHandleReqObj)
        if iden_ret_set is None or iden_ret_set == {}:
            self.handleExceStateFlag = True
            serviceData.logObj.nerror("identify failed!")
            return macBrain_callbackToDjob.call_back_to_djob(200000, dev_id)

        # 决策干扰种类
        decision_ret = dec_decisionMakerMgr.dec_decision_maker_mgr(iden_ret_set)
        if decision_ret == {}:
            self.handleExceStateFlag = True
            serviceData.logObj.nerror("decision failed!")
            return macBrain_callbackToDjob.call_back_to_djob(200000, dev_id)

        # 干扰处理
        opera_ret = op_operatorMgr.Op_operatorMgr(self.brainHandleReqObj, decision_ret)
        if opera_ret:
            self.handleExceStateFlag = True
            serviceData.logObj.nerror("operation failed!")
            return macBrain_callbackToDjob.call_back_to_djob(200000, dev_id)

        self.handleExceStateFlag = True
        self.handleExceRet = 0

        # TODO 回调给Djob
        return macBrain_callbackToDjob.call_back_to_djob(100000, dev_id)

    def is_finished(self):
        return self.handleExceStateFlag
