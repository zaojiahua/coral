import os
import shutil

from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainLib import op_djobWorkThread


class Work4Djob:

    def __init__(self, brain_handle_req_obj, TOItem_id):
        self.brainHandleReqObj = brain_handle_req_obj
        self.TOItemID = TOItem_id

    def prepare(self):
        self.job_id = serviceData.TOItemInfoObj[self.TOItemID].getOpJobId()
        imsrc = self.brainHandleReqObj.referInfo["referImg"]
        self.imdst = os.path.join(self.brainHandleReqObj.getDjobWork(), "reference.png")
        shutil.copy(imsrc, self.imdst)
        if "configPath" in self.brainHandleReqObj.referInfo.keys():
            configSrc = self.brainHandleReqObj.referInfo["configPath"]
            self.configDst = os.path.join(self.brainHandleReqObj.getDjobWork(), "imageAreas.json")
            shutil.copy(configSrc, self.configDst)
        serviceData.logObj.ninfo("copy success!")

    def work(self):
        """
        1.移动文件，下发job,
        2.等待回调， 设定时长
        3.回调时长到，查看文件
        4. macBrain 回调callback
        :return:
        """
        self.prepare()
        dev_id = self.brainHandleReqObj.getDeviceID()
        json_data = {
            "requestName": "insertDJob",
            "DJobDict": {
                "deviceID": dev_id + "_brain",
                "jobID": self.job_id
            },
            "djobSource": "macBrain"
        }
        djobThrdObj = op_djobWorkThread.DjobWorkThread(json_data)
        djobThrdObj.start()
        serviceData.brainHandleOpcbDict[dev_id] = djobThrdObj
        djobThrdObj.join()
        del serviceData.brainHandleOpcbDict[dev_id]
        if djobThrdObj.get_ret() == 0:
            return self.readDjonRet()
        else:
            return 1

    def readDjonRet(self):
        '''
        去dev工作目录下读取结果
        '''
        retPath = os.path.join(self.brainHandleReqObj.getDjobWork(), "isRemoved.txt")
        if not os.path.exists(retPath):
            return 1
        fh = open(retPath, 'r')
        ret = int(fh.read())
        fh.close()
        serviceData.logObj.ninfo("Read Djob Result:   " + str(ret))
        return ret

    def ending(self):
        if os.path.exists(self.imdst):
            os.remove(self.imdst)
        if os.path.exists(self.configDst):
            os.remove(self.configDst)
