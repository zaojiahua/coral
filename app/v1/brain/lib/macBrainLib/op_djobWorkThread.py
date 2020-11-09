import threading
import time

from app.v1.brain.lib import serviceData


class DjobWorkThread(threading.Thread):
    def __init__(self, json_data):
        threading.Thread.__init__(self)
        self.jsonData = json_data
        self.isCb = False
        self.timeout = 240
        self.ret = 1

    def run(self):
        serviceData.reqProxy4DjobSvc.postRequest(self.jsonData)
        serviceData.logObj.ninfo("post Request to Djob......")
        while not self.isCb:
            time.sleep(1)
            self.timeout -= 1
            if self.timeout == 0:
                return self.ret

        self.ret = 0
        serviceData.logObj.ninfo("Djob callBack ok!")
        return 0

    def get_ret(self):
        return self.ret
