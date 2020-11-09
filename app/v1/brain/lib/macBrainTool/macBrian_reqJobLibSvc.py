from app.v1.brain.lib import serviceData


def req_job_lib_svc(job_id):
    js_data = {
        "requestName": "getJobPath",
        "jobLabel": job_id
    }
    serviceData.logObj.ninfo("reqJoblibSvc：" + str(js_data))
    reponse = serviceData.reqProxy4joblSvc.postRequest(js_data)
    # TODO  parsing Reponse
    return reponse
