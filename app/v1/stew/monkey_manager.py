import copy
import json
import traceback
from datetime import datetime
import os
import re
import subprocess
import time

from app.libs.ospathutil import asure_path_exist, deal_dir_file
from app.v1.Cuttle.basic.common_utli import adb_unit_maker, handler_exec
from app.v1.eblock.config.setting import BUG_REPORT_TIMEOUT
from app.config.url import monkey_url
from app.libs.http_client import request

MONKEY_LOG_PATH = 'monkey_log'
RUNNING_LOG = 'monkey_running.log'
ERROR_LOG = 'monkey_error.log'


class MonkeyManager(object):

    device_dict = {}
    push_monkey_script = 'adb -s {device_label} push app/config/monkey.script /sdcard/monkey.script'
    monkey_script = 'adb -s {device_label} shell monkey ' \
                    '-f /sdcard/monkey.script -v -v -v 1 1>{running_log}  2>{error_log}'

    def __new__(cls, *args, **kwargs):
        # 单例
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self):
        pass

    @staticmethod
    def get_execute_result(proc):
        re_str = proc.communicate()[0]
        try:
            execute_result = re_str.strip().decode('utf-8')
        except UnicodeDecodeError:
            execute_result = re_str.strip().decode('gbk')
        return execute_result

    @staticmethod
    def get_monkey_log_path(device_label):
        if ':' in device_label:
            dir_name = device_label.split(':')[0]
        else:
            dir_name = device_label
        log_path = asure_path_exist(os.path.join(MONKEY_LOG_PATH, dir_name))
        return log_path

    # 将设备加入到监控中
    def add_device(self, device_label):
        if device_label not in self.device_dict or self.device_dict[device_label] is None:
            # 首次执行的时候，需要先把脚本推送到手机上，才能执行
            if device_label not in self.device_dict:
                push_proc = subprocess.Popen(self.push_monkey_script.format(device_label=device_label),
                                             shell=True,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT)
                # 脚本推送需要一定的时间
                while push_proc.poll() is None:
                    time.sleep(1)
                print('monkey脚本推送测试机结果：', self.get_execute_result(push_proc))

            # 创建一个目录用来存放日志文件
            log_path = self.get_monkey_log_path(device_label)

            # 该函数返回一个子进程
            monkey_cmd = self.monkey_script.format(device_label=device_label,
                                                   running_log=os.path.join(log_path, RUNNING_LOG),
                                                   error_log=os.path.join(log_path, ERROR_LOG))
            print(monkey_cmd)
            monkey_proc = subprocess.Popen(monkey_cmd,
                                           shell=True,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT)
            # 等待1s再判断是否创建成功
            time.sleep(1)
            if monkey_proc.poll() is None:
                self.device_dict[device_label] = monkey_proc
                print(f'{device_label}创建monkey进程成功：{self.device_dict[device_label].pid}')
            else:
                # 创建失败的时候，打印错误原因
                print(f'{device_label}创建monkey进程失败', self.get_execute_result(monkey_proc))

    # 将设备从监控中移除，因为有设备可能error或者offline
    def remove_device(self, device_label):
        if device_label in self.device_dict:
            # 结束进程
            self.device_dict[device_label].kill()
            del self.device_dict[device_label]

    # 监控的循环
    def monkey_loop(self):
        try:
            while True:
                if self.device_dict:
                    device_labels = copy.deepcopy(list(self.device_dict.keys()))
                    for device_label in device_labels:
                        monkey_proc = self.device_dict[device_label]
                        # 说明monkey脚本不再执行了，这个时候判断究竟是何种异常引发的错误，也有可能是脚本运行完成自动终止了
                        if monkey_proc is not None and monkey_proc.poll() is not None:
                            print('检测是否有异常发生')
                            self.check_exception(device_label)
                            # 重新启动monkey脚本
                            del monkey_proc
                            self.device_dict[device_label] = None
                            self.add_device(device_label)

                # 将设备自动加入进来或者将无用的设备移除出去
                from app.v1.device_common.device_model import Device, DeviceStatus
                for device in Device.all():
                    # 移除
                    if device.status == DeviceStatus.ERROR or device.status == DeviceStatus.OFFLINE:
                        if device.connect_number in self.device_dict:
                            print('monkey移除设备', device.device_label)
                            del self.device_dict[device.connect_number]
                    # 加入
                    else:
                        if device.connect_number and (device.connect_number not in self.device_dict or
                                                      self.device_dict[device.connect_number] is None):
                            print('monkey加入设备', device.device_label)
                            self.add_device(device.connect_number)

                # 隔一秒再检测，不要太快
                time.sleep(1)
        except Exception as e:
            print(traceback.format_exc())

    # 检测是否有异常情况发生
    def check_exception(self, connect_number):
        abnormal_type = None
        package_name = None

        log_path = self.get_monkey_log_path(connect_number)
        log_filename = os.path.join(log_path, ERROR_LOG)
        with open(log_filename, 'rt', encoding='utf-8') as file:
            error_content = file.read()
            if 'device offline' in error_content:
                return

            crash_package = re.findall(r'CRASH:\s+([\w0-9.]+)', error_content)
            anr_package = re.findall(r'ANR in ([\w0-9.]+)', error_content)
            exception_type = re.findall(r'[\w0-9]+Exception', error_content)
            if crash_package:
                abnormal_type = 3
                package_name = crash_package
            elif anr_package:
                abnormal_type = 2
                package_name = anr_package
            elif exception_type:
                abnormal_type = 4
                package_name = exception_type

        # 代表找到了异常信息
        if abnormal_type is not None:
            target_device = None
            from app.v1.device_common.device_model import Device
            for device in Device.all():
                if device.connect_number == connect_number:
                    target_device = device
                    self.bug_report(device.device_label, connect_number, log_path)
                    break

            # 发送相关信息到reef
            files = []
            for filename in os.listdir(log_path):
                file_path = os.path.join(log_path, filename)
                files.append(('files', (filename, open(file_path, 'rb'), 'file')))
            response = request(method="POST",
                               url=monkey_url,
                               data={'abnormity_type': abnormal_type,
                                     'device': target_device.device_label,
                                     'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                     'result_data': json.dumps({'pkg_name': package_name})},
                               files=files)
            print(response)

            # 需要删除日志文件
            deal_dir_file(log_path)

    @staticmethod
    def bug_report(device_label, connect_number, log_path):
        cmd_list = [f"bugreport {log_path}/bugreport.zip"]
        request_body = adb_unit_maker(cmd_list, device_label, connect_number, BUG_REPORT_TIMEOUT)
        handler_exec(request_body, 'AdbHandler')
        print("bug report finished ")
