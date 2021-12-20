import logging
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict

import numpy as np

from app.config.ip import HOST_IP, ADB_TYPE
from app.config.setting import CORAL_TYPE, HARDWARE_MAPPING_LIST
from app.config.log import DOOR_LOG_NAME
from app.config.url import device_create_update_url, device_url, phone_model_url, device_assis_create_update_url, \
    device_assis_url, device_update_url
from app.execption.outer.error_code.adb import DeviceNotInUsb, NoMoreThanOneDevice, DeviceCannotSetprop, \
    DeviceBindFail, DeviceWmSizeFail, DeviceAlreadyInCabinet, ArmNorEnough, AdbConnectFail
from app.execption.outer.error_code.total import RequestException
from app.libs.http_client import request
from app.v1.Cuttle.basic.setting import hand_used_list
from app.v1.Cuttle.macPane.pane_view import PaneConfigView
from app.v1.Cuttle.network.network_api import batch_bind_ip, bind_spec_ip
from app.v1.device_common.device_model import Device
from app.v1.stew.model.aide_monitor import AideMonitor
from app.libs.adbutil import AdbCommand, get_room_version

logger = logging.getLogger(DOOR_LOG_NAME)


class DoorKeeper(object):
    def __init__(self):
        self.adb_cmd_obj = AdbCommand()
        self.today_id = 0
        self.date_mark = None

    def authorize_device(self, **kwargs):
        s_id = self.get_device_connect_id(multi=False)
        dev_info_dict = self.get_device_info(s_id, kwargs)
        logger.info(f"[get device info] device info dict :{dev_info_dict}")
        self.open_wifi_service(num=f"-s {s_id}")
        if ADB_TYPE == 0:
            self.adb_cmd_obj.run_cmd_to_get_result(f"adb connect {dev_info_dict.get('ip_address')}")
            res = bind_spec_ip(dev_info_dict.get("ip_address"), dev_info_dict["device_label"])
            # if res != 0:
            #     raise DeviceBindFail
        else:
            self.is_device_rootable(num=f"-s {s_id}")
        if CORAL_TYPE > 2:
            self.set_arm_or_camera(CORAL_TYPE, dev_info_dict["device_label"])
        self.send_dev_info_to_reef(dev_info_dict.pop("deviceName"),
                                   dev_info_dict)  # now report dev_info_dict to reef directly
        logger.info(f"set device success")
        return 0

    def set_arm_or_camera(self, CORAL_TYPE, device_label):
        port_list = HARDWARE_MAPPING_LIST.copy()
        rotate = True if CORAL_TYPE == 3 else False
        executer = ThreadPoolExecutor()
        # if CORAL_TYPE >= 5:
        #     for port in port_list:
        #         PaneConfigView.hardware_init(port, device_label, executer, rotate=rotate)
        try:
            # 一个机柜只放一台手机限定
            available_port_list = list(set(port_list) ^ set(hand_used_list))
            print("available port list :", available_port_list)
            if len(available_port_list) == 0:
                raise ArmNorEnough
            for port in available_port_list:
                PaneConfigView.hardware_init(port, device_label, executer, rotate=rotate)
                hand_used_list.append(port)
        except IndexError:
            raise ArmNorEnough

    def get_connected_device_list(self, adb_response):
        try:
            # 在adb server没启动的时候，执行第一个命令会启动adb server，这个时候，返回的字符串包含了adb server启动的信息
            adb_response = re.sub(r'[\s\S]*(List of devices attached)', r'\1', adb_response)
        except Exception:
            logger.error('List of devices attached re pattern failed')

        id_list = []
        for i in adb_response.split("\n")[1:]:
            item = i.split(" ")[0]
            try:
                descriptor = i.split(" ")[7]
            except IndexError:
                descriptor = ""
            if not "." in item and not "emulator" in item and "no" != descriptor:
                id_list.append(item.strip().strip("\r\t"))
        return id_list

    def get_already_connected_device_id_list(self):
        response = request(url=device_url, params={"fields": "cpu_id", "status__in": "ReefList[idle{%,%}busy]"})
        assis_response = request(url=device_assis_url, params={"fields": "serial_number", "is_active": True})
        id_list = response.get("devices")
        assis_id_list = assis_response.get("subsidiarydevice")
        return [i.get("cpu_id") for i in id_list] + [i.get("serial_number") for i in assis_id_list]

    def authorize_device_manually(self, **kwargs):
        length = np.hypot(kwargs.get("device_height"), kwargs.get("device_width"))
        # 此处x，y方向的dpi其实可能有差异，但是根据现有数据只能按其相等勾股定理计算，会有一点点误差，但是实际点击基本可以cover住
        kwargs["x_dpi"] = kwargs["y_dpi"] = round(length / float(kwargs.pop("screen_size")), 3)
        kwargs["start_time_key"] = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        kwargs["device_label"] = "M-" + kwargs.get("phone_model_name")
        try:
            response = request(url=phone_model_url, params={"fields": "manufacturer.manufacturer_name",
                                                            "phone_model_name": kwargs.get("phone_model_name")},
                               filter_unique_key=True)
            kwargs["manufacturer"] = response.get("manufacturer").get("manufacturer_name")
        except RequestException:
            kwargs["manufacturer"] = "Manual_device"
        kwargs["rom_version"] = "Manual_"+kwargs["manufacturer"]
        kwargs["android_version"] =  kwargs["cpu_name"] = kwargs[
            "cpu_id"] = "Manual_device"
        kwargs["ip_address"] = "0.0.0.0"
        kwargs["auto_test"] = False
        kwargs["device_type"] = "test_box"
        if CORAL_TYPE > 2:
            self.set_arm_or_camera(CORAL_TYPE, kwargs["device_label"])
        self.send_dev_info_to_reef(kwargs.pop("device_name"), kwargs, with_monitor=False)
        return 0

    def open_device_wifi_service(self, device_id=""):
        # 好像已经作废的方法
        dev_info_dict = self.get_device_info(device_id)

        return dev_info_dict

    # 支持ADB有线 ADB无线 以及各类型机柜
    def reconnect_device(self, device_label):
        # 设备重连，只做获取最新ip和开启5555端口的操作
        if device_label is None or len(device_label) < 1 or CORAL_TYPE >= 5:
            raise AdbConnectFail()

        s_id = device_label.split("---")[-1]
        if ADB_TYPE == 1:
            ip = '0.0.0.0'
        else:
            ip = self.get_dev_ip_address_internal(f"-s {s_id}")
            if ip == "":
                raise AdbConnectFail()

        room_version = get_room_version(s_id)
        android_version = self.adb_cmd_obj.run_cmd_to_get_result(
            f"adb -s {s_id} shell getprop ro.build.version.release")
        manufacturer = self.adb_cmd_obj.run_cmd_to_get_result(
            f"adb -s {s_id} shell getprop ro.product.manufacturer").capitalize()

        not_found = 'not found'
        if not_found in room_version or not_found in android_version or not_found in manufacturer:
            raise AdbConnectFail()

        self.open_wifi_service(f"-s {s_id}")
        return {'ip_address': ip, 'rom_version': room_version, 'device_label': device_label,
                'manufacturer': manufacturer, 'android_version': android_version}

    def update_device_info(self, request_data):
        device_label = request_data.get('device_label')
        ip = request_data.get('ip_address')
        rom_version = request_data.get('rom_version')
        android_version = request_data.get('android_version')
        manufacturer = request_data.get('manufacturer')
        res = request(method="POST", url=device_update_url,
                      json={"ip_address": ip,
                            "rom_version": rom_version,
                            "device_label": device_label,
                            "manufacturer": request_data.get('manufacturer'),
                            "android_version": android_version})
        logger.info(f"response from reef: {res}")
        from app.v1.device_common.device_model import Device
        device_obj = Device(pk=device_label)
        device_obj.ip_address = ip
        device_obj.android_version = android_version
        device_obj.manufacturer = manufacturer
        device_obj.rom_version = rom_version
        return 0

    def open_wifi_service(self, num="-d"):
        rootable = self.is_device_rootable(num)
        if rootable:
            self.is_device_remountable(num)
        wifi_response = self.set_adb_wifi_property_internal(rootable, num)
        if wifi_response != 0 and ADB_TYPE == 0:
            logger.error("Failed to set adb wifi property.")
            raise DeviceCannotSetprop()
        return 0

    def muti_register(self, device_name):
        error_happened = False
        device_dict = dict()
        s_id_list = self.get_device_connect_id(multi=True)
        for index, num in enumerate(s_id_list):
            try:
                dev_info_dict = self.get_device_info(num, {})
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

    def get_device_info(self, s_id, device_info_fict):
        screen_size = self.get_screen_size_internal(f"-s {s_id}")
        ret_dict = {
            "android_version": self.adb_cmd_obj.run_cmd_to_get_result(
                f"adb -s {s_id} shell getprop ro.build.version.release"),
            "device_width": screen_size[0],
            "device_height": screen_size[1], "start_time_key": datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}
        ret_dict = self._get_device_dpi(ret_dict, f"-s {s_id}")
        ret_dict.update(device_info_fict)
        return ret_dict

    def get_device_connect_id(self, multi=False):
        # 获取adb连接的所有设备，并与已经注册过的设备取差集，得到唯一待注册设备，差集为0或大于1都抛异常
        adb_response = self.adb_cmd_obj.run_cmd_to_get_result("adb -d devices -l", 12)
        if "device usb" not in adb_response and "device product" not in adb_response and "device transport_id" not in adb_response:
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
        # 正则匹配手机信息内对应位置的dpi值，如有新版本手机可能需要更改此处来抓到对应dpi的值
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
        # 通过adb拿设备信息，第一次只拿必要的，需要用户确认的信息。待用户确认后，再通过set接口拿其余信息并彻底注册
        s_id = self.get_device_connect_id(multi=False)
        # 不同手机机型名称放置的位置不同，现在只已知小米手机+oppo部分机型的情况，有新机型可能需要加逻辑
        phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.oppo.market.name")
        old_phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.product")
        productName = phone_model if len(phone_model) != 0 else old_phone_model
        ret_dict = {"phone_model_name": productName,
                    "cpu_name": self.adb_cmd_obj.run_cmd_to_get_result(
                        f"adb -s {s_id} shell getprop ro.board.platform"),
                    "manufacturer": self.adb_cmd_obj.run_cmd_to_get_result(
                        f"adb -s {s_id} shell getprop ro.product.manufacturer").capitalize(),
                    "cpu_id": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.serialno"),
                    "ip_address": self.get_dev_ip_address_internal(f"-s {s_id}")}
        ret_dict["device_label"] = (old_phone_model + "---" + ret_dict["cpu_name"] + "---" + ret_dict["cpu_id"])
        self._check_device_already_in_cabinet(ret_dict["device_label"])
        # rom version数据不同类型手机可能藏在不同的地方，oppo已知型号要去拿color_os+版本， mi的直接拿ro.build.version.incremental
        ret_dict["rom_version"] = get_room_version(s_id)

        # 判定是否为未见过的机型，是-->手机内获取机型信息   否-->从reef缓存机型信息
        phone_model_info_dict, status = self.is_new_phone_model(productName)
        if not status:
            ret_dict.update(phone_model_info_dict)
        else:
            ret_dict = self._get_device_dpi(ret_dict, f"-s {s_id}")
        logger.info(f"[get device info] device info dict :{ret_dict}")
        return ret_dict

    def get_assis_device(self):
        s_id = self.get_device_connect_id(multi=False)
        phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.oppo.market.name")
        old_phone_model = self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.build.product")
        productName = phone_model if len(phone_model) != 0 else old_phone_model
        ret_dict = {"phone_model_name": productName,
                    "ip_address": self.get_dev_ip_address_internal(f"-s {s_id}") if ADB_TYPE == 0 else '0.0.0.0',
                    "device_label": self.adb_cmd_obj.run_cmd_to_get_result(f"adb -s {s_id} shell getprop ro.serialno"),
                    "manufacturer": self.adb_cmd_obj.run_cmd_to_get_result(
                        f"adb -s {s_id} shell getprop ro.product.manufacturer").capitalize()
                    }
        check_params = {"fields": "is_active", "serial_number": ret_dict["device_label"]}
        response = request(url=device_assis_url, params=check_params)
        try:
            if not response.get("subsidiarydevice")[0].get("is_active") == False:
                raise DeviceAlreadyInCabinet
        except IndexError:
            pass
        phone_model_info_dict, status = self.is_new_phone_model(productName)
        if not status:
            ret_dict.update(phone_model_info_dict)
        else:
            ret_dict = self._get_device_dpi(ret_dict, f"-s {s_id}")
        logger.info(f"[get device info] device info dict :{ret_dict}")
        self.is_device_rootable(num=f"-s {s_id}")
        return ret_dict

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
        if ADB_TYPE == 0:
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
            "fields": "phone_model_name,x_border,y_border,x_dpi,y_dpi"
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
        if "already running" in root_response:
            return True
        elif "restarting adbd" in root_response:
            time.sleep(2)
            return True
        return False

    def is_device_remountable(self, num="-d"):
        return True if 0 == self.adb_cmd_obj.run_cmd(f"adb {num} remount", "remount succeeded", 1, 5) else False

    def set_adb_wifi_property_internal(self, rootable, num="-d"):
        # 对有root权限手机，永久打开5555端口，没有的只能临时打开，重启就会失效，需要重新走此流程
        if rootable:
            for i in range(3):
                self.adb_cmd_obj.run_cmd(f"adb {num} shell setprop persist.adb.tcp.port 5555")
                if 0 == self.adb_cmd_obj.run_cmd(f"adb {num} shell getprop persist.adb.tcp.port", "5555"):
                    self.adb_cmd_obj.run_cmd(f"adb {num} tcpip 5555")
                    return 0
            return -1
        else:
            for i in range(3):
                self.adb_cmd_obj.run_cmd(f"adb {num} shell setprop service.adb.tcp.port 5555")
                self.adb_cmd_obj.run_cmd(f"adb {num} tcpip 5555")
                time.sleep(1.5)
                if 0 == self.adb_cmd_obj.run_cmd(f"adb {num} shell getprop service.adb.tcp.port", "5555"):
                    return 0
            return -2

    def set_tmac_client_apk_internal(self, remountable):
        # 很久很久之前的需要推送到手机的配置文件和apk，目前已经不需要了。
        dev_client_apk_file = "tstMacCli.apk"
        dev_reg_config_file = "TstMacCli.conf"

        if remountable:
            # for remountable devices: 1. push apk+conf
            self.adb_cmd_obj.run_cmd("adb -d push " + dev_client_apk_file + " /system/app/")
            self.adb_cmd_obj.run_cmd("adb -d push " + dev_reg_config_file + " /system/etc/")
            self.adb_cmd_obj.run_cmd("adb -d reboot")
        return 0

    def send_dev_info_to_reef(self, device_name, dev_data_dict, with_monitor=True):
        # 设备信息推到reef，更新本地redis缓存，开启此设备的loop
        if device_name == "":
            device_name = self.get_default_name()
        dev_data_dict["device_name"] = device_name  # add device name before post to pane
        dev_data_dict["cabinet"] = HOST_IP.split(".")[-1]
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
        # 对于没起名字的手机，给默认名规则为NewDevice月日-序号 eg：NewDevice0702-001
        real_date = datetime.now().strftime("%m-%d")
        if not real_date == self.date_mark:
            self.date_mark = real_date
            self.today_id = 0  # reset to zero in a new day
        device_name = "NewDevice" + real_date + "-" + "{:0>3s}".format(str(self.today_id))  # NewDevice0702-001
        self.today_id += 1
        return device_name

    def get_dev_ip_address_internal(self, num):
        ret_ip_address = "0.0.0.0"
        # ip_route "10.80.6.0/24 dev wlan0  proto kernel  scope link  src 10.80.6.153"
        ip_route = self.adb_cmd_obj.run_cmd_to_get_result(f"adb {num} shell ip route")
        result = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", ip_route)
        if result:
            ret_ip_address = result[-1]
        return ret_ip_address

    def get_screen_size_internal(self, num):
        # 获取设备分辨率 eg 1080*2160
        ret_size_list = []
        tmp_str = self.adb_cmd_obj.run_cmd_to_get_result(f"adb {num} shell wm size", timeout=5)
        override_size = re.findall(r'Override size:\s+([0-9]+)x([0-9]+)', tmp_str)
        physical_size = re.findall(r'Physical size:\s+([0-9]+)x([0-9]+)', tmp_str)
        if len(override_size) > 0 and len(override_size[0]) == 2:
            target_size = override_size
        elif len(physical_size) > 0 and len(physical_size[0]) == 2:
            target_size = physical_size
        else:
            target_size = None

        if target_size is not None:
            ret_size_list.append(int(target_size[0][0]))
            ret_size_list.append(int(target_size[0][1]))
        else:
            raise DeviceWmSizeFail

        return ret_size_list
