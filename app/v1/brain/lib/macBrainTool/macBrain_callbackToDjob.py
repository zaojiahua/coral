from app.v1.brain.lib import serviceData


def call_back_to_djob(ret_code, dev_id):
    # retCode = 100000  | 200000
    json_data = {"requestName": "setEBlkDone",
                 "deviceID": dev_id,
                 "blkIndex": ret_code}
    serviceData.reqProxy4DjobSvc.postRequest(json_data)
    return 0
