import subprocess


# 重启coral容器
def restart_coral():
    subprocess.Popen('kill 1',
                     shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
