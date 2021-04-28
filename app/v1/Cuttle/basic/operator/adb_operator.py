import os
import re
import subprocess
import sys
import time
from ast import literal_eval
from datetime import datetime

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import PROJECT_SIBLING_DIR
from app.config.url import battery_url
from app.execption.outer.error_code.total import ServerError
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.chinese_calculater import ChineseMixin
from app.v1.Cuttle.basic.operator.handler import Handler, Abnormal
from app.v1.Cuttle.basic.setting import adb_disconnect_threshold, normal_result
from app.v1.Cuttle.boxSvc.box_views import on_or_off_singal_port

adb_cmd_prefix = "adb "
if sys.platform.startswith("win"):
    coding = "utf-8"
    mark = "\r\n"
    find_command = "findstr"
else:
    coding = "utf-8"
    mark = "\n"
    find_command = "grep"


class AdbHandler(Handler, ChineseMixin):
    discharging_mark_list = ["Discharging", "Not charging"]
    process_list = [
        # mark 为str 因为adb func 返回str
        Abnormal(mark="restarting adbd as root", method="reconnect", code=-6),
        Abnormal("device offline", "reconnect", -5),
        #  此处windows和linux 有较多区别，windows下不能保证完全正常运行
        Abnormal("inaccessible or not found", "ignore", -8),
        Abnormal("not found", "reconnect", -3),
        Abnormal("protocol fault", "reconnect", -2),
        Abnormal("daemon not running", "reconnect", -1),
        Abnormal("unable to connect", "reconnect", -7),
        Abnormal("battery mark", "save_battery", 0),
        Abnormal("cpu", "save_cpu_info", 0),
        Abnormal("battery fail mark", "_get_battery_detail", 0)
    ]
    before_match_rules = {
        # 根据cmd中内容，执行对应的预处理方法
        "shell input text": '_chinese_input',
        "input tap": "_relative_point",
        "input swipe": "_relative_swipe",
        "G01": "_ignore_unsupported_commend"
    }

    def before_execute(self, *args, **kwargs):
        if self._model.is_connected == False:
            self.reconnect()
        for key, value in self.before_match_rules.items():
            if key in self.exec_content:
                return getattr(self, value)()
        return False, None

    def str_func(self, exec_content, **kwargs) -> str:
        exec_content = self._compatible_sleep(exec_content)
        self._model.logger.debug(f"adb input:{exec_content}")
        if len(exec_content) == 0:
            return ""
        sub_proc = subprocess.Popen(exec_content, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        restr = sub_proc.communicate()[0]
        time.sleep(1)
        try:
            execute_result = restr.strip().decode(coding)
        except UnicodeDecodeError:
            execute_result = restr.strip().decode("gbk")
            print("cmd to exec:", exec_content, "decode error happened")
        self._model.logger.debug(f"adb response:{execute_result}")
        return execute_result

    def reconnect(self, *args):
        if ADB_TYPE == 1:
            self.str_func(adb_cmd_prefix + "kill-server" )
            self.str_func(adb_cmd_prefix + "start-server" )
            self._model.is_connected = True
            return 0
        if self.kwargs.get("assist_device_serial_number"):
            device_ip = self.kwargs.get("assist_device_serial_number")
        else:
            from app.v1.device_common.device_model import Device
            device_ip = Device(pk=self._model.pk).ip_address
        if len(device_ip) < 2:
            return -1
        self.str_func(adb_cmd_prefix + "disconnect " + device_ip)
        self.str_func(adb_cmd_prefix + "-s " + device_ip + " tcpip 5555")
        self.str_func(adb_cmd_prefix + "connect " + device_ip)
        self.str_func(adb_cmd_prefix + "-s " + device_ip + ":5555 " + "root")
        self.str_func(adb_cmd_prefix + "-s " + device_ip + ":5555 " + "remount")
        self._model.is_connected = True
        self._model.disconnect_times += 1
        if self._model.disconnect_times >= adb_disconnect_threshold:
            pass  # todo send reef to set device disconnect
        return 0

    def disconnect(self, ip=None):
        if ADB_TYPE == 1:
            return 0
        from app.v1.device_common.device_model import Device
        device_ip = Device(pk=self._model.pk).ip_address if ip is None else ip
        self.str_func(adb_cmd_prefix + "disconnect " + device_ip)
        if hasattr(self._model, "is_connected"):
            self._model.is_connected = False
        return 0

    def _compatible_sleep(self, exec_content):
        if "<4ccmd>" in exec_content:
            exec_content = exec_content.replace("<4ccmd>", '')
        if "<sleep>" in exec_content:
            res = re.search("<sleep>(.*?)$", exec_content)
            sleep_time = res.group(1)
            time.sleep(float(sleep_time))
            exec_content = exec_content.replace("<sleep>" + sleep_time, "").strip()
        return exec_content

    def save_cpu_info(self, result):
        regex = re.compile("(.*?)cpu .*(.*?)idle")
        result = re.findall(regex, result)
        pass

    def save_battery(self, result):
        from app.v1.device_common.device_model import Device
        result_list = result.split(mark)
        battery_level = int(result_list[0])
        charging = False if result_list[1].strip() in self.discharging_mark_list else True
        if int(battery_level) <= 10 and charging == False:
            on_or_off_singal_port({
                "port": Device(pk=self._model.pk).power_port,
                "action": True
            })
        self._model.disconnect_times = 0
        try:
            json_data = {
                "device": Device(pk=self._model.pk).id,
                "cabinet": HOST_IP.split(".")[-1],
                "record_datetime": datetime.now(),
                "battery_level": battery_level,
                "charging": charging
            }
            response = request(method="POST", url=battery_url, data=json_data)
            self._model.logger.info(f"push battery to reef response:{response}")
        except ServerError:
            pass

    def adb_save(self, *args):
        battery_path = os.path.join(PROJECT_SIBLING_DIR, "Pacific", self._model.pk, "djobBattery", "battery.dat")
        try:
            if os.path.exists(battery_path):
                self._get_battery_info(battery_path, self._model.pk, self._model.logger)
                os.remove(battery_path)
        except (PermissionError, FileNotFoundError) as e:
            self._model.logger.error(f"exception :{repr(e)}")

    def after_unit(self):
        time.sleep(0.5)

    def _get_battery_detail(self, *args):
        from app.v1.device_common.device_model import Device
        device_ip = Device(pk=self._model.pk).connect_number
        battery_detail = self.str_func(adb_cmd_prefix + "-s " + device_ip + " shell dumpsys battery")
        self._get_battery_info(battery_detail)

    def _get_battery_info(self, battery_data):
        """
        标准格式：
            AC powered: false
            USB powered: true
            Wireless powered: false
            Max charging current: 500000
            Max charging voltage: 5000000
            Charge counter: 127490
            status: 2
            health: 2
            present: true
            level: 2
            scale: 100
            voltage: 3617
            temperature: 360
            technology: Li-poly

            battery.dat 可能不是标准格式，可能很大

            获取电量(battery_level)和充放电状态(charging)，当未获取到时提示err_log
        """

        def filter_fields(re_compile, text):
            match_list = re.compile(re_compile).findall(text)
            return match_list[0] if match_list else None

        def get_value(item, regex, line):
            if item is None:
                return filter_fields(regex, line)
            else:
                return item

        ac_power, usb_power, battery_level = None, None, None
        for line in battery_data.split("\n"):
            ac_power = get_value(ac_power, r"AC powered: (true|false)", line.strip("\r"))
            usb_power = get_value(usb_power, r"USB powered: (true|false)", line.strip("\r"))
            battery_level = get_value(battery_level, r"level: ([0-9]+)", line.strip("\r"))
            if ac_power is not None and usb_power is not None and battery_level is not None:
                break

        if ac_power is None and usb_power is None:
            self._model.logger.error("Get the battery.dat file but unable to obtain charge state")
            return
        if battery_level is None:
            self._model.logger.error("Get the battery.dat file but unable to obtain power")
            return
        from app.v1.device_common.device_model import Device
        from app.libs.http_client import request
        json_data = {
            "device": Device(pk=self._model.pk).id,
            "cabinet": HOST_IP.split(".")[-1],
            "record_datetime": datetime.now(),
            "battery_level": int(battery_level),
            "charging": literal_eval(ac_power.capitalize()) or literal_eval(usb_power.capitalize())
        }
        self._model.logger.debug(f"send battery info to reef:{json_data}")
        self._model.disconnect_times = 0
        try:
            response = request(method="POST", url=battery_url, data=json_data)
            self._model.logger.info(f"push battery to reef response:{response}")
        except ServerError:
            pass
        return 0

    def ignore(self, *args):
        pass

    def _chinese_input(self):
        regex = re.compile("shell input text ([\u4e00-\u9fa5]*).*")
        result = re.search(regex, self.exec_content)
        if result is None:
            return False, None
        words = result.group(1)
        if self.is_chinese(words):
            return True, self.chinese_support(words)
        else:
            return False, None




    def _ignore_unsupported_commend(self):
        return True, -9
