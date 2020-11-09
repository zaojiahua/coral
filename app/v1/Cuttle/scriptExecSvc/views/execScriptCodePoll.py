from app.v1.Cuttle.scriptExecSvc.lib import execScriptMain
from app.v1.Cuttle.scriptExecSvc.lib.jsonUtil import get_value


def exec_script_code_poll(workdata):
    thread_name = get_value("threadName", workdata)
    return execScriptMain.exec_script_code_poll(thread_name)
