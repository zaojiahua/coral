import threading
import time

from app.v1.brain.lib import serviceData


class ExecBlockWorkThread(threading.Thread):
    def __init__(self, post_js_data, timeout):
        threading.Thread.__init__(self)
        self.postJsdata = post_js_data
        self.timeout = timeout  # TODO  timeoue will be definded  in TOItem-UUID json file.
        self.isFinished = False
        self.eBlkRes = 1
        self.isCallbacked = False

    def run(self):
        print("ready to send ....", self.postJsdata)
        serviceData.reqProxy4eblkSvc.postRequest(self.postJsdata)
        time_tick = 0
        while time_tick < self.timeout:
            time.sleep(1)
            if self.isCallbacked:
                self.eBlkRes = 0
                return 0
            time_tick += 1
        return 1

    def getEblkRes(self):
        return self.eBlkRes
