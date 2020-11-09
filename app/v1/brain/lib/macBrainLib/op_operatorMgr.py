"""
此部分作为清除干扰的操作者部分的管理者
是操作者部分的唯一入口，也是唯一出口
"""
from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainLib import op_deliver4eBlk, op_work4Djob

"""
inputParam:"TOItem_uuid"
"""


def op_operatorMgr(brain_handle_req_obj, TOItem_id):
    '''
    1. 拿到block,查看有没有需要替换的
    2. 有需要替换的就替换
    3. 下发给EBLK
    4. 等待回调
    5. 超时不回调，默认失败
    6. 回调后查看结果，给Djob 回调
    '''
    exec_module = serviceData.TOItemInfoObj[TOItem_id].getOpExecModule()
    serviceData.logObj.ninfo("execModule: " + exec_module)
    if exec_module == 'Djob':
        ret = op_work4Djob.Work4Djob(brain_handle_req_obj, TOItem_id)
        return ret.work()
    elif exec_module == 'EBLK':
        eblk_dict = serviceData.TOItemInfoObj[TOItem_id].getOpDict()
        # 向Eblk发送执行模块请求
        delive_eblk_obj = op_deliver4eBlk.Deliver4eBlk(brain_handle_req_obj, eblk_dict)
        delive_work_thread = delive_eblk_obj.proc_and_dispatch()
        serviceData.brainHandleOpcbDict[brain_handle_req_obj.getDeviceID()] = deliveWorkThread
        delive_work_thread.join()
        if delive_work_thread.getEblkRes:
            del serviceData.brainHandleOpcbDict[brain_handle_req_obj.getDeviceID()]
            return 1
        del serviceData.brainHandleOpcbDict[brain_handle_req_obj.getDeviceID()]
        return 0
    else:
        return 1
