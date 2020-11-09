from app.v1.Cuttle.scriptExecSvc.lib.execScriptMain import exec_script_main
from app.v1.Cuttle.scriptExecSvc.lib.jsonUtil import get_value


def exec_script_code(workdata):
    """
    support file :   .py   .lua  .class  .jar
    :param workdata:
    :return:
    """
    script_code_type = get_value("scriptCodetype", workdata)
    exec_cmd = get_value("execCmd", workdata)
    return exec_script_main(script_code_type, exec_cmd)