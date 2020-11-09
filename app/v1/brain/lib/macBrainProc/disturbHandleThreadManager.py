from . import brainHandleThread


class DisturbHandleThreadManager():

    def __init__(self):
        self.brainHandleThreadMgr = {}

    def start_req_handle_thrd(self, brain_handle_req_info_obj):
        dev_id = brain_handle_req_info_obj.get_device_id()
        if dev_id in self.brainHandleThreadMgr.keys():
            del self.brainHandleThreadMgr[dev_id]
        # 开启处理线程
        self.brainHandleThreadMgr[dev_id] = brainHandleThread.BrainHandleThread(brain_handle_req_info_obj)
        self.brainHandleThreadMgr[dev_id].start()
        return 0
