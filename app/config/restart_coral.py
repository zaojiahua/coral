import subprocess


# 重启coral容器
def restart_coral():
    subprocess.Popen('docker restart machexec_container',
                     shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
