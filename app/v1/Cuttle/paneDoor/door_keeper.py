import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict

import numpy as np

from app.config.ip import HOST_IP
from app.config.log import DOOR_LOG_NAME
from app.config.url import device_create_update_url, device_url, phone_model_url, device_assis_create_update_url, \
    device_assis_url
from app.execption.outer.error_code.adb import DeviceNotInUsb, NoMoreThanOneDevice, DeviceChanged, DeviceCannotSetprop, \
    DeviceBindFail, DeviceWmSizeFail, DeviceAlreadyInCabinet
from app.execption.outer.error_code.total import RequestException
from app.libs.http_client import request
from app.v1.Cuttle.network.network_api import batch_bind_ip, bind_spec_ip
from app.v1.device_common.device_model import Device
from app.v1.stew.model.aide_monitor import AideMonitor

logger = logging.getLogger(DOOR_LOG_NAME)


class DoorKeeper(object):
    def __init__(self):
        self.adb_cmd_obj = AdbCommand()
        self.today_id = 0
        self.date_mark = None

    def authorize_device(self, **kwargs):
        s_id = self.get_device_connect_id(multi=False)
        dev_info_dict = self.get_device_info(s_id)
        device_id = kwargs.pop("deviceID")
        if device_id != "" and device_id != dev_info_dict["device_label"]:
            logger.warning("set device idle is not equal with usb device")
            raise DeviceChanged
        logger.info(f"[get device info] device info dict :{dev_info_dict}")
        self.open_wifi_service(num=f"-s {s_id}")
        self.adb_cmd_obj.run_cmd_to_get_result(f"adb connect {dev_info_dict.get('ip_address')}")
        # self.set_tmac_client_apk_internal(remountable)
        res = bind_spec_ip(dev_info_dict.get("ip_address"), dev_info_dict["device_label"])
        # if res != 0:
        #     raise DeviceBindFail
        dev_info_dict.update(kwargs)
        self.send_dev_info_to_reef(kwargs.pop("deviceName"), dev_info_dict)  # now report dev_info_dict to reef directly
        logger.info(f"set device success")
        return 0

    def get_connected_device_list(self, adb_response):
        id_list = []
        for i in adb_response.split("\n")[1:]:
            item = i.split(" ")[0]
            if not "." in item and not "emulator" in item and not "no permissions" in item:
                id_list.append(item.strip().strip("\r\t"))
        return id_list

    def get_already_connected_device_id_list(self):
        response = request(url=device_url, params={"fields": "cpu_id", "status__in": "ReefList[idle{%,%}busy]"})
        id_list = response.get("devices")
        return [i.get("cpu_id") for i in id_list]

    def authorize_device_manually(self, **kwargs):
        length = np.hypot(kwargs.get("device_height"), kwargs.get("device_width"))
        kwargs["x_dpi"] = kwargs["y_dpi"] = length / float(kwargs.pop("screen_size"))
        kwargs["start_time_key"] = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        kwargs["device_label"] = "M-" + kwargs.get("phone_model_name") + "-" + kwargs.get("device_name", "DefaultName")
        kwargs["manufacturer"] = kwargs["android_version"] = kwargs["rom_version"] = kwargs["cpu_name"] = kwargs[
            "cpu_id"] = "Manual_device"
        kwargs["ip_address"] = "0.0.0.0"
        kwargs["auto_test"] = False
        kwargs["device_type"] = "test_box"
        self.send_dev_info_to_reef(kwargs.pop("device_name"), kwargs, with_monitor=False)
        return 0

    def open_device_wifi_service(self, device_id=""):
        dev_info_dict = self.get_device_info(device_id)

        return dev_info_dict

    def reconnect_device(self, device_label):
        if device_label is None or len(device_label) < 1:
            return -1
        s_id = device_label.split("---")[-1]
        ip = self.get_dev_ip_address_internal(f"-s {s_id}")
        if ip == "":
            raise DeviceNotInUsb
        from app.v1.device_common.device_model import Device
        res = request(method="PATCH", url=device_url + str(Device(pk=device_label).id) + "/",
                      json={"ip_address": ip})
        logger.info(f"response from reef: {res}")
        return self.open_wifi_service(f"-s {s_id}")


    def open_wifi_service(self, num="-d"):
        rootable = self.is_device_rootable(num)
        remountable = self.is_device_remountable(num)
        if remountable == 2:
            rootable = self.is_device_rootable(num)
            self.is_device_remountable(num)
        wifi_response = self.set_adb_wifi_property_internal(rootable, num)
        if wifi_response != 0:
            logger.error("Failed to set adb wifi property.")
            raise DeviceCannotSetprop
        return 0

    def muti_register(self, device_name):
        error_happened = False
        device_dict = dict()
        s_id_list = self.get_device_connect_id(multi=True)
        for index, num in enumerate(s_id_list):
            try:
                dev_info_dict = self.get_device_info(num)
                device_name_with_number = device_name + str(index + 1)
                self.send_dev_info_to_reef(device_name_with_number, dev_info_dict)
                self.show_device_name(str(index + 1), num=f"-s {num}")
                device_dict[dev_info_dict.get("ip_address")] = dev_info_dict.get("device_label")
            except Exception as e:
                error_happened = True
                logger.error(f"muti-register fail for device {num},{repr(e)}")
                continue
        response = batch_bind_ip(device_dict)
        if response == -1:
            raise DeviceBindFail
        res = {"status": "ok"} if not error_happened else {"status": "some device success while others fail"}
        return res

    def show_device_name(self, index, num, ):
        self.adb_cmd_obj.run_cmd_to_get_result(
            f"adb {num} shell am start -a android.intent.action.VIEW -d http://{HOST_IP}:5000/static/{index}.png")

    def get_device_info(self, s_id):
        screen_size = self.get_screen_size_internal(f"-s {s_id}")
        phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.oppo.market.name")
        old_phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.product")
        phone_model = phone_model if len(phone_model) != 0 else old_phone_model
        ret_dict = {
            "cpu_name": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.board.platform"),
            "cpu_id": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.serialno"),
            "android_version": self.adb_cmd_obj.run_cmd_to_get_result(
                f"adb -s {s_id} shell getprop ro.build.version.release"),
            "manufacturer": self.adb_cmd_obj.run_cmd_to_get_result(
                f"adb -s {s_id} shell getprop ro.product.manufacturer").capitalize(),
            "ip_address": self.get_dev_ip_address_internal(f"-s {s_id}"),
            "device_width": screen_size[0],
            "device_height": screen_size[1],
            "start_time_key": datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
            "phone_model_name": phone_model
        }
        color_os = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.version.opporom")
        rom_version = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.display.ota")
        if len(rom_version) == 0:
            rom_version = self.adb_cmd_obj.run_cmd_to_get_result("adb -d shell getprop ro.build.display.id")
        ret_dict["rom_version"] = color_os + "_" + rom_version if rom_version is not "" and color_os is not "" else \
            self.adb_cmd_obj.run_cmd_to_get_result("adb -d shell getprop ro.build.version.incremental")
        ret_dict = self._get_device_dpi(ret_dict, f"-s {s_id}")
        ret_dict["device_label"] = old_phone_model + "---" + ret_dict["cpu_name"] + "---" + ret_dict["cpu_id"]
        return ret_dict

    def get_device_connect_id(self, multi=False):
        adb_response = self.adb_cmd_obj.run_cmd_to_get_result("adb -d devices -l", 6)
        if "device usb" not in adb_response and "device product" not in adb_response:
            logger.info("[get device info]: no device found")
            raise DeviceNotInUsb  # no device found
        device_id_list = self.get_connected_device_list(adb_response)
        device_exist_id_list = self.get_already_connected_device_id_list()
        register_id_list = list(set(device_id_list).difference(set(device_exist_id_list)))
        if len(register_id_list) == 0:
            raise DeviceNotInUsb
        if not multi:
            if len(register_id_list) > 1:
                raise NoMoreThanOneDevice
            else:
                return register_id_list[0]
        else:
            return register_id_list

    def _get_device_dpi(self, ret_dict, num):
        try:
            keyword = "findstr" if sys.platform.startswith("win") else "grep"
            result_words = self.adb_cmd_obj.run_cmd_to_get_result(
                f"adb {num} shell dumpsys window displays |{keyword} dpi")
            dpi = re.search("\((.*?) x (.*?)\)", result_words)
            ret_dict["x_dpi"] = dpi.group(1)
            ret_dict["y_dpi"] = dpi.group(2)
            return ret_dict
        except AttributeError as e:
            return ret_dict

    def get_device_info_compatibility(self):
        s_id = self.get_device_connect_id(multi=False)
        phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.oppo.market.name")
        old_phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.product")
        productName = phone_model if len(phone_model) != 0 else old_phone_model
        ret_dict = {
            "productName": productName,
            "cpuName": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.board.platform"),
            "cpuID": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.serialno"),
            # "buildVer": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.version.release"),
            "ipAddress": self.get_dev_ip_address_internal(f"-s {s_id}"),
            # "startTimeKey": datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        }
        # color_os = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.version.opporom")
        # romVersion = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.display.ota")
        # if len(romVersion) == 0:
        #     romVersion = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.display.id")
        # ret_dict["buildInc"] = color_os + "_" + romVersion if romVersion is not "" and color_os is not "" else \
        #     self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.version.incremental")
        ret_dict["deviceID"] = (old_phone_model + "---" + ret_dict["cpuName"] + "---" + ret_dict["cpuID"])
        self._check_device_already_in_cabinet(ret_dict["deviceID"])
        phone_model_info_dict, status = self.is_new_phone_model(productName)
        if not status:
            ret_dict.update(phone_model_info_dict)
        else:
            ret_dict = self._get_device_dpi(ret_dict, f"-s {s_id}")
        logger.info(f"[get device info] device info dict :{ret_dict}")
        return ret_dict

    def get_assis_device(self):
        s_id = self.get_device_connect_id(multi=False)
        cpu_id = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.serialno")
        check_params = {"fields": "is_active", "serial_number": cpu_id}
        response = request(url=device_assis_url, params=check_params)
        try:
            if not response.get("subsidiarydevice")[0].get("is_active") == False:
                raise DeviceAlreadyInCabinet
        except IndexError:
            pass
        device_info_dict = {
            "serial_number": cpu_id,
            "ip_address": self.get_dev_ip_address_internal(f"-s {s_id}")
        }
        return device_info_dict

    def set_assis_device(self, **kwargs):
        # {
        #     "serial_number": "1231234",
        #     "ip_address": "127.0.0.6",
        #     "order": 1,
        #     "is_active": true,
        #     "devices": [
        #         1
        #     ]
        # }
        self.open_wifi_service(f"-s {kwargs.get('serial_number')}")
        kwargs["is_active"] = True
        res = request(method="POST", url=device_assis_create_update_url, json=kwargs)
        logger.info(f"response from reef: {res}")
        # device_object = Device(pk=kwargs["device_label"])
        # setattr(device_object, "assis_" + kwargs.get("order"), kwargs.get("ip_address"))
        return 0

    def is_new_phone_model(self, phone_model) -> (Dict, bool):
        params = {
            "phone_model_name": phone_model,
            "fields": "id,phone_model_name,x_border,y_border,x_dpi,y_dpi"
        }
        try:
            response = request(url=phone_model_url, params=params, filter_unique_key=True)
            return response, False
        except RequestException:
            return {}, True

    def _check_device_already_in_cabinet(self, device_label):
        params = {
            "device_label": device_label,
            "fields": "cabinet.ip_address",
            "status__in": "ReefList[idle{%,%}busy]"
        }
        try:
            request(url=device_url, params=params, filter_unique_key=True)
            raise DeviceAlreadyInCabinet
        except RequestException:
            pass


    def is_device_connected(self):
        tmp_ret_str = self.adb_cmd_obj.run_cmd_to_get_result("adb -d devices -l", 6)
        if "device usb" not in tmp_ret_str and "device product" not in tmp_ret_str:
            return False  # no device found
        return True

    def is_device_rootable(self, num="-d"):
        # "adbd is already running as root" or "restarting adbd as root" or "error: device not found" or cannot run root in production mode
        root_response = self.adb_cmd_obj.run_cmd_to_get_result(f"adb {num} root", 3)
        if "already running" in root_response or "restarting adbd" in root_response:
            return True
        return False

    def is_device_remountable(self, num="-d"):
        return True if 0 == self.adb_cmd_obj.run_cmd(f"adb {num} remount", "remount succeeded", 1, 5)else False


    def set_adb_wifi_property_internal(self, rootable, num="-d"):
        if rootable:
            for i in range(3):
                self.adb_cmd_obj.run_cmd(f"adb {num} shell setprop persist.adb.tcp.port 5555")
                if 0 == self.adb_cmd_obj.run_cmd(f"adb {num} shell getprop persist.adb.tcp.port", "5555"):
                    return 0
            return -1
        else:
            for i in range(3):
                self.adb_cmd_obj.run_cmd(f"adb {num} shell setprop service.adb.tcp.port 5555")
                self.adb_cmd_obj.run_cmd(f"adb {num} tcpip 5555")
                time.sleep(1)
                if 0 == self.adb_cmd_obj.run_cmd(f"adb {num} shell getprop service.adb.tcp.port", "5555"):
                    return 0
            return -2

    def set_tmac_client_apk_internal(self, remountable):
        dev_client_apk_file = "tstMacCli.apk"
        dev_reg_config_file = "TstMacCli.conf"

        if remountable:
            # for remountable devices: 1. push apk+conf
            self.adb_cmd_obj.run_cmd("adb -d push " + dev_client_apk_file + " /system/app/")
            self.adb_cmd_obj.run_cmd("adb -d push " + dev_reg_config_file + " /system/etc/")
            self.adb_cmd_obj.run_cmd("adb -d reboot")
        return 0

    def send_dev_info_to_reef(self, device_name, dev_data_dict, with_monitor=True):
        if device_name == "":
            device_name = self.get_default_name()
        dev_data_dict["device_name"] = device_name  # add device name before post to pane
        dev_data_dict["cabinet"] = HOST_IP.split(".")[-2]
        # -----add none for adjustment---
        dev_data_dict["instance_port"] = None  # add device name before post to pane
        logger.debug(f"send device create request to reef {dev_data_dict}")
        res = request(method="POST", url=device_create_update_url, json=dev_data_dict)
        logger.info(f"response from reef: {res}")

        dev_data_dict["id"] = res.get("id") if res.get("id") else 0
        device_object = Device(pk=dev_data_dict["device_label"])
        device_object.update_attr(**dev_data_dict, avoid_push=True)
        aide_monitor_instance = AideMonitor(device_object)
        t = threading.Thread(target=device_object.start_device_sequence_loop, args=(aide_monitor_instance,))
        t.setName(dev_data_dict["device_label"])
        t.start()
        if with_monitor:
            ThreadPoolExecutor(max_workers=100).submit(device_object.start_device_async_loop, aide_monitor_instance)

    def get_default_name(self):
        real_date = datetime.now().strftime("%m_%d")
        if not real_date == self.date_mark:
            self.date_mark = real_date
            self.today_id = 0  # reset to zero in a new day
        device_name = "NewDevice" + real_date + "-" + "{:0>3s}".format(str(self.today_id))  # NewDevice0702-001
        self.today_id += 1
        return device_name

    def get_dev_ip_address_internal(self, num):
        ret_ip_address = ""
        # ip_route "10.80.6.0/24 dev wlan0  proto kernel  scope link  src 10.80.6.153"
        ip_route = self.adb_cmd_obj.run_cmd_to_get_result(f"adb {num} shell ip route")
        result = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", ip_route)
        if result:
            ret_ip_address = result[-1]
        return ret_ip_address

    def get_screen_size_internal(self, num):
        ret_size_list = []
        tmp_str = self.adb_cmd_obj.run_cmd_to_get_result(f"adb {num} shell wm size")
        tmp_list = tmp_str.split("Physical size: ")
        if len(tmp_list) > 1:
            tmp_str = tmp_list[1]
            tmp_list = tmp_str.split("x")
            if len(tmp_list) > 1:
                ret_size_list.append(int(tmp_list[0]))
                ret_size_list.append(int(tmp_list[1]))
        if len(ret_size_list) == 0:
            raise DeviceWmSizeFail
        return ret_size_list


class AdbCommand(object):
    def __init__(self):
        if sys.platform.startswith("win"):
            self.adbCmdPrefix = "adb "
        else:
            self.adbCmdPrefix = "~/bin/adb "
        self.subproc = None

    def make_one_cmd(self, *commands):
        command_string = self.adbCmdPrefix
        for c in commands:
            command_string += (" " + c)
        return command_string

    def run_cmd(self, one_adb_cmd_string, expect_result="", retry=1, timeout=3):
        for r in range(0, retry):
            if 0 == self.run_cmd_internal(one_adb_cmd_string, expect_result, timeout):
                return 0
        return 1

    def run_cmd_to_get_result(self, one_cmd_string, timeout=3):
        logger.debug("runCmdToGetResult : " + one_cmd_string + ", timeout: " + str(timeout))
        run_thread = ShellCmdThread(one_cmd_string)
        run_thread.start()
        result = ""
        for r in range(timeout * 2):
            time.sleep(0.5)
            if run_thread.is_finished():
                result = run_thread.get_result()
                run_thread = ShellCmdThread(one_cmd_string)
                run_thread.start()
                logger.debug("adbCmd run get result: " + str(result))
                break
        if not run_thread.is_finished():
            run_thread.terminate_thread()
        return result

    def run_cmd_internal(self, one_cmd_string, expect_result, timeout):
        logger.debug("adbCmd run: " + one_cmd_string + ", expect: " + expect_result + ", timeout: " + str(timeout))
        run_thread = ShellCmdThread(one_cmd_string)
        run_thread.start()
        result = ""
        for r in range(timeout * 2):
            time.sleep(0.5)
            if run_thread.is_finished():
                result = run_thread.get_result()
                logger.debug("adbCmd run get result: " + str(result))
                break
        if not run_thread.is_finished():
            run_thread.terminate_thread()
            return -1
        if (len(expect_result) > 0) and (expect_result in result):
            return 0
        return 1

    def fix_command(self):
        logger.warning("receive problem of device offline, try to kill adb server")
        self.subproc = subprocess.Popen("adb kill-server", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.subproc.wait()
        self.subproc = subprocess.Popen("adb start-server", shell=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
        self.subproc.wait()
        self.subproc = subprocess.Popen("adb root", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.subproc.wait()
        self.subproc = subprocess.Popen("adb remount", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.subproc.wait()


class ShellCmdThread(threading.Thread):
    def __init__(self, one_cmd_string):
        threading.Thread.__init__(self)
        self.isExeDone = False
        self.oneCmdString = one_cmd_string
        self.exeResult = ""
        self.subproc = None

    def run(self):
        self.isExeDone = False
        logger.debug("exeThread running " + self.oneCmdString + os.linesep)
        self.subproc = subprocess.Popen(self.oneCmdString, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        restr = self.subproc.communicate()[0]
        self.exeResult = restr.strip().decode()
        logger.debug("ShellCmdThread run end return " + self.exeResult + os.linesep)
        self.isExeDone = True

    def is_finished(self):
        return self.isExeDone

    def get_result(self):
        return self.exeResult

    def terminate_thread(self):
        if (not self.isExeDone) and (self.subproc is not None):
            try:
                self.subproc.terminate()
            except Exception as e:
                logger.error("Got exception in ShellCmdThread-terminateThread: " + str(e))
        return 0


if __name__ == '__main__':
    a = DoorKeeper()
    result = a.get_mutidevice_list()
    print(result)
