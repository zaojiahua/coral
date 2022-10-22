import subprocess
import time


# 重启coral容器 函数执行过程中，不应该再次调用
def restart_coral():
    subprocess.Popen('kill 1',
                     shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(60)
