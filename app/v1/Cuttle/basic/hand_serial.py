import time

import serial
from serial import SerialException

from mcush import *

from app.config.setting import CORAL_TYPE, usb_power_com
from app.execption.outer.error_code.hands import ControlUSBPowerFail
from app.v1.Cuttle.basic.setting import Z_UP, arm_wait_position


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

    def recv(self, buffer_size=32):
        # print(self.ser.read(buffer_size))
        try:
            rev = self.ser.read(buffer_size).decode()
        except SerialException:
            raise
        print('返回：', rev, '*' * 10)
        if 'ok' in rev or 'unlock' in rev:
            return 0
        return -1

    def close(self):
        self.ser.close()
        return 0

    def write(self, content):
        print('before-写入机械臂：', content)
        if content == "<SLEEP>":
            time.sleep(0.8)
            return ""
        print('写入机械臂：', self.ser, content)
        return self.ser.write(content.encode())


def controlUsbPower(status="ON"):
    try:
        s = ShellLab.ShellLab(usb_power_com)

        s.pinOutputLow('0.0')
        s.pinOutputLow('0.1')
        s.pinOutputLow('0.2')
        s.pinOutputLow('0.3')

        if status == "ON":
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
        print("Control usb power fail, info: ", str(e))
        raise ControlUSBPowerFail
