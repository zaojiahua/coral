import time

from app.v1.Cuttle.scriptExecSvc.lib import serviceData, execScriptCodeThread


def exec_script_main(script_code_type, exec_cmd):
    """
    接受参数 开启线程
    线程需要的参数是不定长的  输入参数拼成命令行
    在serviceData里面存一个字典保存{"threadName":{"<pressTime>":"27s"}}
    或者返回值是否需要写进文件里
    先处理python   之后考虑java的运行代码
    :param script_code_type:
    :param exec_cmd:
    :return:
    """
    thread_name = script_code_type + " -- " + str(time.time())
    exec_thread = execScriptCodeThread.ExecScriptCodeThread(thread_name, script_code_type, exec_cmd)
    exec_thread.start()
    exec_thread_name = exec_thread.getName()
    serviceData.execThreadPool[exec_thread_name] = exec_thread
    ret_js_data = {"execThreadName": exec_thread_name}
    # 返回值为执行线程的Name[String]
    return ret_js_data


def exec_script_code_poll(thread_name):
    if thread_name in list(serviceData.execThreadPool.keys()):
        ret_data = {"result": 1}
    else:
        ret_data = {"result": 0}
    return ret_data
