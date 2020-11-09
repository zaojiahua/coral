import subprocess
import threading

from app.v1.Cuttle.scriptExecSvc.lib import serviceData


class ExecScriptCodeThread(threading.Thread):

    def __init__(self, thread_name, script_code_type, exec_cmd):
        threading.Thread.__init__(self)
        self.threadName = thread_name
        self.setName(self.threadName)
        self.script_code_type = script_code_type
        self.execCmd = exec_cmd
        self.debug = True

    def run(self):
        exec_cmd_string = self.script_code_type + " " + self.execCmd
        # self.subproc = subprocess.Popen(self.oneCmdString, shell=True, stdout=subprocess.PIPE)
        sub_proc = subprocess.Popen(exec_cmd_string, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        res_str = sub_proc.communicate()[0]
        exec_result = res_str.strip().decode()  # print(self.exeResult)
        print(exec_result)
        del serviceData.execThreadPool[self.threadName]
        return 0
