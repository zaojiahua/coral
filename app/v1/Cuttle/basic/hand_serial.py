import re
import time

import serial
from serial import SerialException

from mcush import *

from app.config.setting import CORAL_TYPE, usb_power_com, camera_power_com
from app.execption.outer.error_code.hands import ControlUSBPowerFail
from app.v1.Cuttle.basic.setting import arm_wait_position, camera_power_close, camera_power_open


class HandSerial:

    def __init__(self, baud_rate=115200, timeout=5):
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None

    def connect(self, com_id):
        self.ser = serial.Serial(com_id, self.baud_rate, timeout=self.timeout)
        return 0

    def send_single_order(self, g_order):
        return self.write(g_order)

    def send_out_key_order(self, g_orders, others_orders, wait_time=0, **kwargs):
        deviate_order = arm_wait_position
        for o_order in g_orders:
            self.write(o_order)
        if wait_time != 0:
            time.sleep(wait_time)
        for other_order in others_orders:
            self.write(other_order)
        self.write(deviate_order)
        return 0

    def send_list_order(self, g_orders, **kwargs):
        deviate_order = arm_wait_position
        if kwargs.get("wait"):
            for g_order in g_orders:
                self.write(g_order)
            time.sleep(float(kwargs.get("wait_time", 2000)) / 1000)
            other_orders = kwargs.get('other_orders', [])
            for o_order in other_orders:
                self.write(o_order)
            self.write(deviate_order)
            return 0
        elif kwargs.get("ignore_reset") or CORAL_TYPE < 5:
            for g_order in g_orders:
                self.write(g_order)
            return 0
        else:
            g_orders.append(deviate_order)
            for g_order in g_orders:
                self.write(g_order)
            return 0

    def send_and_read(self, g_orders, **kwargs):
        for order in g_orders:
            self.write(order)
            rev = self.ser.read(8).decode()
            print("rev: ", rev)
        self.write(arm_wait_position)
        self.ser.read(8).decode()
        if CORAL_TYPE == 5.3:
            time.sleep(3)
        else:
            time.sleep(2)
        return 0

    def check_hand_status(self, buffer_size=64):
        # 查询机械臂状态
        self.ser.write("G04 P0.1 \r\n".encode())
        self.ser.write("?? \r\n".encode())
        try:
            rev = self.ser.read(buffer_size).decode()
        except SerialException:
            return False
        if "Idle" in rev:
            return True
        return False

    def recv(self, buffer_size=32, is_init=False, **kwargs):
        # print(self.ser.read(buffer_size))
        try:
            rev = self.ser.read(buffer_size).decode()
        except SerialException as se:
            if "no data" not in se.args[0]:
                raise
            rev = "ok"
        print('返回：', rev, '*' * 10)
        while not is_init and not self.check_hand_status():
            time.sleep(0.2)
        print("当前动作执行完毕")
        if 'ok' in rev or 'unlock' in rev:
            return 0
        return -1

    def close(self):
        self.ser.close()
        return 0

    def write(self, content):
        print(f'{self.ser.port} before-写入机械臂：', content)
        if content == "<SLEEP>":
            time.sleep(0.8)
            return ""
        # print('写入机械臂：', self.ser, content)
        return self.ser.write(content.encode())


def controlUsbPower(status="ON"):
    try:
        s = ShellLab.ShellLab(usb_power_com)

        s.pinOutputLow('0.0')
        s.pinOutputLow('0.1')
        s.pinOutputLow('0.2')
        s.pinOutputLow('0.3')

        if status == "ON" or status == "init":
            s.pinSetHigh('0.0')
            s.pinSetHigh('0.3')
            s.pinSetHigh('0.1')
            s.pinSetHigh('0.2')
        else:
            s.pinSetLow('0.0')
            s.pinSetLow('0.3')
            s.pinSetLow('0.1')
            s.pinSetLow('0.2')
        return 0
    except Exception as e:
        if status == "init":
            return 0
        print("Control usb power fail, info: ", str(e))
        raise ControlUSBPowerFail


# 相机的触发控制
class CameraUsbPower(object):

    def __new__(cls, *args, **kwargs):
        # 确保自己为单例对象
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self, power_com=camera_power_com, timeout=1):
        if not hasattr(self, "s"):
            self.s = ShellLab.ShellLab(power_com)
        self.timeout = timeout
        self.line_number = 1.7

    def __enter__(self):
        self.open()
        return self.s

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # 开启同步信号
    def open(self):
        print('------发送同步信号-----')
        self.s.pinSetHigh(self.line_number)
        self.s.pinOutputHigh(self.line_number)

    # 结束同步信号
    def close(self):
        time.sleep(self.timeout)
        self.s.pinSetLow(self.line_number)
        print('-------结束同步信号-----')


class CameraPower(HandSerial, CameraUsbPower):
    def __init__(self, power_com=camera_power_com, baud_rate=9600, timeout=1):
        HandSerial.__init__(self, baud_rate)
        self.timeout = timeout
        if self.ser is None:
            self.connect(power_com)

    def __enter__(self):
        self.open()
        return self

    def open(self):
        print('------CameraPower发送同步信号-----')
        self.send_data()

    def close(self):
        self.send_data(action="close")
        print('-------CameraPower结束同步信号-----')

    def send_data(self, action="open"):
        order = camera_power_open if action == "open" else camera_power_close
        send_order = bytes.fromhex(order)
        self.ser.write(send_order)  # 发送数据
        return_data = self.ser.read(16)  # 读取缓冲数据
        str_return_data = str(return_data.hex())
        print("收到的回复是：", str_return_data)
        if str_return_data == order:
            return 0
        raise Exception("外触发控制器出现问题")


# 传感器控制
class SensorSerial(HandSerial):

    def send_read_order(self):
        order = "FE 01 07 01 02 00 01 cf fc cc ff"
        send_data = bytes.fromhex(order)
        self.ser.write(send_data)

    # 读取按压的力值
    def query_sensor_value(self):
        regex = re.compile("fe0150[\w+]*cffcccff")

        for i in range(3):
            return_data = self.ser.read(24)
            str_return_data = str(return_data.hex())
            result = re.search(regex, str_return_data)
            if result is None:
                continue
            data = result.group(0)[:22]
            print("data: ", data)
            if len(data) != 22 or data[6:16] == "f" * 8:
                pass
            value = int(data[12:14], 16) / 10
            print("取到的力值：", value)
            return value
        return 0
