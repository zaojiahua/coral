import os

from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainProc import disturbCheck, brainHandleRequest


def disturb_check_a_handle(dut_dict, refer_img, refer_img_area, input_img_file, text_list, isHandle=True):
    # TODO Separate disturbCheck and disturbHandle
    try:
        brain_handle_req_info_obj = brainHandleRequest.BrainHandleRequest(refer_img, refer_img_area, dut_dict,
                                                                          input_img_file,
                                                                          text_list)
        checker = disturbCheck.DisturbCheck(brain_handle_req_info_obj)
        if checker.check():
            # disturb handle!
            serviceData.brainHandleThrdMgr.StartReqHandleThrd(brain_handle_req_info_obj)
            serviceData.logObj.ninfo("To Djob is : running!")
            return {"status": "running"}
        else:
            # no distrub!
            serviceData.logObj.ninfo("To Djob is ：ok!")
            return {"state": "OK"}
    except Exception as e:
        serviceData.logObj.nerror(str(e) + os.linesep)
        return {"error": "invalid"}

    # brainHandleReqInfoObj = brainHandleRequest.BrainHandleRequest(referInfo, dutDict, inputImgFile, textlist)
    # if brainHandleReqInfoObj.getDeviceID() == "dior---msm8226---c1a65aca":
    #     if macBrian_callADBC.callAdbc() == 0:
    #         return {"state":"OK"}
    #     else:
    #         return {"status":"running"}
    # else:
    #     return {"state":"OK"}
