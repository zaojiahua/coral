import os
import random
import re
import shutil
import subprocess
import sys
import time
from ast import literal_eval
from datetime import datetime
from threading import Lock

from func_timeout import func_set_timeout

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import PROJECT_SIBLING_DIR, CORAL_TYPE, Bugreport_file_name
from app.config.url import battery_url
from app.execption.outer.error_code.total import ServerError
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.chinese_calculater import ChineseMixin
from app.v1.Cuttle.basic.operator.handler import Handler, Abnormal
from app.v1.Cuttle.basic.setting import adb_disconnect_threshold, get_lock_cmd, unlock_cmd, \
    adb_cmd_prefix, RESTART_SERVER, KILL_SERVER, START_SERVER, DEVICE_DETECT_ERROR_MAX_TIME, get_global_value
from app.v1.Cuttle.boxSvc.box_setting import port_charge_strategy
from app.v1.Cuttle.boxSvc.box_views import on_or_off_singal_port
from app.v1.eblock.config.setting import ADB_DEFAULT_TIMEOUT

if sys.platform.startswith("win"):
    coding = "utf-8"
    mark = "\r\n"
else:
    coding = "utf-8"
    mark = "\n"

lock = Lock()


class AdbHandler(Handler, ChineseMixin):
    discharging_mark_list = ["Discharging", "Not charging"]
    process_list = [
        # mark 为str 因为adb func 返回str
        Abnormal(mark="error: closed", method="reconnect", code=-7),
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
        Abnormal("battery fail mark", "_get_battery_detail", 0),
        Abnormal(f"generating {Bugreport_file_name}", "_get_zipfile", 0),  # pulling bug_report.zip
        #     adb: device failed to take a zipped bugreport: Bugreport read terminated abnormally
        Abnormal('Bug report finished but could not be copied to', 'pull_bugreport', 0),
        Abnormal('device failed to take a zipped bugreport', 'retry_bugreport', 0)
    ]
    before_match_rules = {
        # 根据cmd中内容，执行对应的预处理方法
        "shell input text": '_chinese_input',
        "input tap": "_relative_point",
        "input swipe": "_relative_swipe",
        "G01": "_ignore_unsupported_commend"
    }
    NoSleepList = ["screencap -p ", "pull /sdcard/", "shell rm"]

    def before_execute(self, *args, **kwargs):
        for key, value in self.before_match_rules.items():
            if key in self.exec_content:
                return getattr(self, value)()
        return False, None

    def str_func(self, exec_content, **kwargs) -> str:
        exec_content = self._compatible_sleep(exec_content)
        self._model.logger.debug(f"adb input:{exec_content}")
        if len(exec_content) == 0:
            return ""

        # 有俩种类型的锁，俩种类型的操作互斥，一个是adb server start 或者是 kill的，另一个是其他类的
        target_lock = kwargs.get('target_lock')
        lock_type = kwargs.get('lock_type')
        random_value = kwargs.get('random_value')
        while True:
            if target_lock and lock_type:
                is_lock = get_lock_cmd(keys=[target_lock], args=[lock_type, random_value])
                self._model.logger.debug(f"锁状态：{is_lock}")
            else:
                is_lock = 0

            if not is_lock:
                if exec_content == (adb_cmd_prefix + RESTART_SERVER):
                    # restart server 本身也应该是互斥的，否则会出现端口占用等异常
                    lock.acquire(timeout=10)
                    try:
                        for cmd in [adb_cmd_prefix + KILL_SERVER, adb_cmd_prefix + START_SERVER]:
                            sub_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                                        stderr=subprocess.STDOUT)
                            restr = sub_proc.communicate()[0]
                            execute_result = restr.strip().decode(coding)
                            print(f'restart: {cmd} response: {execute_result}')
                    finally:
                        if lock_type:
                            unlock_cmd(keys=[lock_type], args=[random_value])
                        lock.release()
                        break
                else:
                    sub_proc = subprocess.Popen(exec_content, shell=True, stdout=subprocess.PIPE,
                                                stderr=subprocess.STDOUT)
                    restr = sub_proc.communicate()[0]
                    no_sleep = False
                    for cmd in self.NoSleepList:
                        if cmd in exec_content:
                            no_sleep = True
                            break
                    if not no_sleep:
                        time.sleep(1)
                    try:
                        execute_result = restr.strip().decode(coding)
                    except UnicodeDecodeError:
                        execute_result = restr.strip().decode("gbk")
                        print("cmd to exec:", exec_content, "decode error happened")
                    finally:
                        if lock_type:
                            unlock_cmd(keys=[lock_type], args=[random_value])
                        break
            time.sleep(1)

        self._model.logger.debug(f"adb response:{execute_result}")
        return execute_result

    def reconnect(self, *args):
        if CORAL_TYPE < 5:
            if ADB_TYPE == 1:
                pass
                # 有线模式下无论主僚机都做kill&start处理 其他线程也在使用adb server，这里kill掉的话，会导致其他unit执行失败
                # self.do(adb_cmd_prefix + RESTART_SERVER)
            else:
                if self.kwargs.get("assist_device_serial_number"):
                    # 无线模式下主僚机分别取对应的ip进行重连
                    device_ip = self.kwargs.get("assist_device_serial_number")
                else:
                    from app.v1.device_common.device_model import Device
                    device_ip = Device(pk=self._model.pk).ip_address
                if len(device_ip) < 2:
                    return -1
                self.str_func(adb_cmd_prefix + "disconnect " + device_ip)
                self.str_func(adb_cmd_prefix + "-s " + device_ip + " tcpip 5555")
                self.str_func(adb_cmd_prefix + "connect " + device_ip + ":5555")
                self.str_func(adb_cmd_prefix + "-s " + device_ip + ":5555 " + "root")
                self.str_func(adb_cmd_prefix + "-s " + device_ip + ":5555 " + "remount")

            # 如果有连续3次发生连接不上的异常，则判定为error状态 不改变僚机的状态
            if not self.kwargs.get("assist_device_serial_number"):
                self._model.disconnect_times += 1
                self._model.logger.info(f"disconnect_times:{self._model.disconnect_times}")
            if self._model.disconnect_times == 1:
                self._model.disconnect_times_timestamp.ltrim(1, 0)
            self._model.disconnect_times_timestamp.rpush(int(time.time()))
            # 次数和时间双保险
            if self._model.disconnect_times >= adb_disconnect_threshold and \
                    self._model.disconnect_times_timestamp[-1] - self._model.disconnect_times_timestamp[0] > \
                    DEVICE_DETECT_ERROR_MAX_TIME:
                from app.v1.device_common.device_model import DeviceStatus
                self._model.update_device_status(DeviceStatus.ERROR)
                self._model.logger.warning(f"设备状态变成error")
        return 0

    def disconnect(self, ip=None):
        if ADB_TYPE == 1:
            return 0
        from app.v1.device_common.device_model import Device
        device_ip = Device(pk=self._model.pk).ip_address if ip is None else ip
        self.str_func(adb_cmd_prefix + "disconnect " + device_ip)
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
        # 原来Coral的充电逻辑
        # if int(battery_level) <= 10 and charging == False:
        #     on_or_off_singal_port({
        #         "port": Device(pk=self._model.pk).power_port,
        #         "action": True
        #     })
        # 2022.3.31  根据充电口的充电策略进行充电
        self._model.logger.debug(f"根据充电策略充电.....battery_level: {battery_level}")
        self.set_power_port_status_by_battery(battery_level)

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

    def _get_zipfile(self, *args):
        if os.path.exists(f"./{Bugreport_file_name}"):
            shutil.move(f"./{Bugreport_file_name}", self.kwargs.get("work_path"))

    def retry_bugreport(self, result):
        self._model.logger.info(f'bugreport 重新拉取 retry bugreport {result}')
        time.sleep(random.randint(60, 120))
        ret_str = self.str_func(self.exec_content)
        self._model.logger.info(f'bugreport 返回 {ret_str}')

    def pull_bugreport(self, result, *args):
        self._model.logger.info('bugreport 重新拉取')
        # bug report 可能拉取不成功 一种情况是手机内存满 这个没法处理 需要用户自己删除 另一种是写入到本地目录不成功 这个时候重新拉取试试
        command = re.findall(r'but could not be copied to \'(.*)\'[\s\S]*Try to run \'(.*)\'', result)
        if command and len(command[0]) == 2:
            target_command = command[0][1].replace('<directory>', command[0][0])
            self._model.logger.info(target_command)
            from app.v1.device_common.device_model import Device
            device_ip = Device(pk=self._model.pk).connect_number
            self.str_func(adb_cmd_prefix + "-s " + device_ip + f" {target_command}")

    @func_set_timeout(timeout=ADB_DEFAULT_TIMEOUT)
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
        self._model.logger.debug(f"battery fail mark, 根据充电策略充电.....battery_level: {battery_level}")
        self.set_power_port_status_by_battery(battery_level)
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

    def set_power_port_status_by_battery(self, battery_level):
        from app.v1.device_common.device_model import Device
        port = Device(pk=self._model.pk).power_port
        if not port:
            return

        def compare_battery_level(max_level, min_level, level):
            if level <= min_level:
                print("当前电量低于mix_level, 开始充电")
                on_or_off_singal_port({
                    "port": port,
                    "action": True
                })
            elif level >= max_level:
                print("当前电量高于max_level, 停止充电")
                on_or_off_singal_port({
                    "port": port,
                    "action": False
                })

        port_slg = get_global_value("port_charge_strategy")[port]
        print("当前绑定端口是：", port, "当前端口充电策略是：", port_slg)
        slgs_by_user: list[dict] = port_slg["set_by_user_slg"]
        is_use_slgs_by_user = False
        if slgs_by_user:
            # 存在定时充电策略
            for slg in slgs_by_user:
                # 获取当前时间戳,判断是否有包含当前时间点的定时策略
                current_time = time.strftime('%H:%M', time.localtime())
                if slg["timer"][0] <= current_time < slg["timer"][1]:
                    is_use_slgs_by_user = True
                    print("当前使用了定时充电策略： ", slg)
                    compare_battery_level(int(slg["max_value"]), int(slg["min_value"]), int(battery_level))

        if not is_use_slgs_by_user:
            # 未找到包含当前时间点的定时充电策略，或者当前充电端口不存在定时充电策略
            # 则使用默认充电策略
            print("当前使用了默认充电策略： ", port_slg["default_slg"])
            compare_battery_level(int(port_slg["default_slg"]["max_value"]), int(port_slg["default_slg"]["min_value"]),
                                  int(battery_level))
        return 0
