import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.config.setting import BASE_DIR, HOST_IP, CORAL_TYPE, HARDWARE_MAPPING_LIST
from app.config.url import device_url, device_logout, coordinate_url
from app.execption.outer.error import APIException
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.libs.thread_extensions import executor_callback
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.basic.setting import hand_used_list
from app.v1.Cuttle.macPane.pane_view import PaneConfigView
from app.v1.device_common.device_model import Device
from app.v1.stew.model.aide_monitor import AideMonitor

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
    param = {"status__in": "ReefList[idle{%,%}busy]",
             "cabinet_id": HOST_IP.split(".")[-1],
             "fields": "id,auto_test,device_name,device_width,cpu_id,device_height,ip_address,tempport,tempport.port,powerport,powerport.port,device_label,android_version,android_version.version,monitor_index,monitor_index.port,phone_model.phone_model_name,phone_model.x_border,phone_model.y_border,phone_model.cpu_name,phone_model.manufacturer,phone_model.id,phone_model.x_dpi,phone_model.y_dpi,phone_model.manufacturer.manufacturer_name,rom_version,rom_version.version,paneslot.paneview.type,paneslot.paneview.camera,paneslot.paneview.id,paneslot.paneview.robot_arm"}
    res = request(url=device_url, params=param)
    for device_dict in res.get("devices"):
        device_obj = Device(pk=device_dict.get("device_label"))
        device_obj.update_attr(**device_dict)
        try:
            # 再确保恢复属性后恢复testbox相关机械臂和摄像头状态
            # if device_dict.get("paneslot").get("paneview").get("type") == "test_box":
            if CORAL_TYPE >= 3:
                executer = ThreadPoolExecutor()
                # for key in key_parameter_list:
                #     port = device_dict.get("paneslot").get("paneview").get(key)
                port_list = HARDWARE_MAPPING_LIST.copy()
                rotate = True if CORAL_TYPE == 3 else False
                for port in port_list:
                    PaneConfigView.hardware_init(port, device_dict.get("device_label"), executer, rotate=rotate)
                    hand_used_list.append(port)
                set_border(device_dict, device_obj)
        except (AttributeError, APIException):
            pass
        # start a loop for each device when recover+
        recover_root(device_obj.device_label, device_obj.connect_number)
        aide_monitor_instance = AideMonitor(device_obj)
        t = threading.Thread(target=device_obj.start_device_sequence_loop, args=(aide_monitor_instance,))
        t.setName(device_dict.get("device_label"))
        t.start()
        if CORAL_TYPE!= 5:
            executer.submit(device_obj.start_device_async_loop, aide_monitor_instance)


def recover_root(device_label, connect_num):
    cmd_list = [
        f"adb  -s {connect_num} root",
    ]
    jsdata = {}
    jsdata["ip_address"] = connect_num
    jsdata["device_label"] = device_label
    jsdata["execCmdList"] = cmd_list
    UnitFactory().create("AdbHandler", jsdata)


def set_border(device_dict, device_obj):
    # 没放进paneview时候，这个request会向上抛attribute error，
    params = {
        "pane_view": device_dict.get("paneslot").get("paneview").get("id"),
        "phone_model": device_dict.get("phone_model").get("id")
    }
    res = request(url=coordinate_url, params=params)
    if len(res) <1:
        return
    device_obj.update_device_border(res[0])
    # y_border = (res.get("inside_upper_left_x") - res.get("outside_upper_left_x") + (
    #         res.get("outside_under_right_x") - res.get("inside_under_right_x"))) / 2
    # x_border = (res.get("inside_upper_left_y") - res.get("outside_upper_left_y") + (
    #             res.get("outside_under_right_y") - res.get("inside_under_right_y"))) / 2
    # device_obj.x_border = x_border
    # device_obj.y_border = y_border


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
