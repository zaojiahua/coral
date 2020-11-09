from app.v1.brain.lib.macBrainLib import op_execBlockWorkThread


class Deliver4eBlk(object):

    def __init__(self, brain_handle_req_obj, exec_block):
        self.brainHandleReqObj = brain_handle_req_obj
        self.execUnitList = exec_block

    def proc_and_dispatch(self):
        # start work+poll thread for execBlock
        js_data = {"requestName": "insertExecBlock",
                   "dutDict": self.brainHandleReqObj.getDutDict(),
                   "blkSource": "Brain",
                   "eBlkIndex": 0,
                   "eBlkDict": self.execUnitList}
        work_thread = op_execBlockWorkThread.ExecBlockWorkThread(jsdata, 60)
        work_thread.start()
        return work_thread

    def pro_exec_eblk_dict(self):
        # TODO  将传过来的eBlkDict进行恰当处理转换为API需要的格式;  读取任务执行完成需要的时间
        eBlk_dict = {}
        return eBlk_dict
