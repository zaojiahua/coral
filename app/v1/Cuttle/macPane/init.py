import json
import os
import re
import subprocess
import threading
import time
import math
from concurrent.futures import ThreadPoolExecutor

from app.config.setting import BASE_DIR, HOST_IP, CORAL_TYPE
from app.config.url import device_url, device_logout
from app.execption.outer.error import APIException
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.device_common.device_model import Device, DeviceStatus
from app.v1.stew.model.aide_monitor import AideMonitor
from app.v1.Cuttle.paneDoor.door_keeper import DoorKeeper
from app.v1.stew.monkey_manager import MonkeyManager

key_parameter_list = ["camera", "robot_arm"]


def pane_init():
    logger = setup_logger('pane_init', r'pane_init.log')
    reason = check_boot_up_reason()
    executer = ThreadPoolExecutor(max_workers=300)
    if not reason:
        logger.info("---abnormal reboot---, try to set all device to offline")
        clean_device(logger, executer)
    else:
        logger.info("---system update---, try to recover device status ")
        recover_device(executer, logger)


def check_boot_up_reason():
    """
    :return: 0--> clearn   1--->recorver  else-->do nothing
    """
    boot_up_reason = os.path.join(os.path.dirname(BASE_DIR), "source", "bootUpReason.json")
    if not os.path.exists(boot_up_reason):
        return 0
    with open(boot_up_reason, "r") as f:
        file_content = json.load(f)
        reason = file_content.get("startReason")
        reason_code = 1 if reason == "sysUpdate" else 0
    # os.remove(boot_up_reason)
    return reason_code


def clean_device(logger, executer):
    # todo change into one api when reef supported
    param = {"status": "idle", "fields": "id,device_label", "cabinet_id": HOST_IP.split(".")[-1]}
    res = request(url=device_url, params=param)
    for device in res.get("devices"):
        executer.submit(send_device_leave_to_reef, device, logger).add_done_callback(executor_callback)


def send_device_leave_to_reef(device, logger):
    reef_id = device.get("id")
    del_res = request(method="POST", url=device_logout, json={"id": reef_id})
    logger.info(f"clearn device {reef_id}, result:{del_res}")


def recover_device(executer, logger):
    # monkey监控策略
    if math.floor(CORAL_TYPE) < 5:
        executer.submit(MonkeyManager().monkey_loop)

    res = Device.request_device_info()
    for device_dict in res.get("devices"):
        device_label = device_dict.get('device_label')
        print('获取到的设备信息有：', device_label)
        device_obj = Device(pk=device_label)
        device_obj.update_attr(**device_dict)

        try:
            # 1和2类型的柜子，不涉及到其他硬件，3往上的会涉及到其他硬件，所以需要初始化
            if CORAL_TYPE >= 3:
                DoorKeeper.set_arm_or_camera(device_label)
        except (AttributeError, APIException) as e:
            print(repr(e))
            pass

        aide_monitor_instance = AideMonitor(device_obj)

        # 5类型的柜子，都没有ADB
        if device_obj.status != DeviceStatus.ERROR and math.floor(CORAL_TYPE) < 5:
            # 获取root权限
            recover_root(device_obj.device_label, device_obj.connect_number)
            # 获取电量信息
            executer.submit(device_obj.start_device_async_loop, aide_monitor_instance)

        # 开启执行任务的线程
        t = threading.Thread(target=device_obj.start_device_sequence_loop, args=(aide_monitor_instance,))
        t.setName(device_label)
        t.start()


def recover_root(device_label, connect_num):
    cmd_list = [
        f"adb  -s {connect_num} root",
    ]
    jsdata = {}
    jsdata["ip_address"] = connect_num
    jsdata["device_label"] = device_label
    jsdata["execCmdList"] = cmd_list
    jsdata['max_retry_time'] = 1
    UnitFactory().create("AdbHandler", jsdata)


def get_tty_device_number() -> list:
    sub_proc = subprocess.Popen("ls /dev/", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    restr = sub_proc.communicate()[0].decode("utf-8")
    tty_device_list = []
    for i in restr.split('\n'):
        result = re.search("(ttyUSB\d)", i)
        if result:
            tty_device_list.append(result.group())
            print(result.group())
            sub_proc = subprocess.Popen(f"chmod 777 /dev/{result.group()}", shell=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
            response  = sub_proc.communicate()[0].decode("utf-8")
            print(response)
    return tty_device_list


def record_feature(feature_list):
    while True:
        for i in feature_list:
            i[2].info(f"sequence_future: {i[0]._state}   async_future:{i[1]._state} ")
        time.sleep(10)
