import time

from app.v1.brain.lib import serviceData


def call_adbc():
    exec_block_dict = {"deviceIPaddress": "10.80.3.134", "execUnitList": [{"execCmdList": [
        "<3adbcTool> shell input swipe 358 1039 0 1039"
    ],
        "bkupCmdList": [], "exptResList": []}]}

    js_data = {"requestName": "AddaExecBlock", "execBlockName": "dior---msm8226---c1a65aca",
              "execBlockDict": exec_block_dict}
    serviceData.reqProxy4adbcSvc.postRequest(js_data)
    duration = 0
    while (duration < 20):
        duration += 1
        time.sleep(0.5)
        js_data_poll = {"requestName": "AddaExecBlockPoll", "deviceID": "dior---msm8226---c1a65aca"}
        # if svcJsonRequestDef.postReqResponse_DONE == serviceData.reqProxy4adbcSvc.postRequest(js_data_poll):
        #     return 0
    return -1
