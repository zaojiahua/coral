import time

import serial

from app.config.setting import CORAL_TYPE
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
        return self.ser.write(g_order.encode())

    def send_list_order(self, g_orders, **kwargs):
        deviate_order = arm_wait_position
        if kwargs.get("wait"):
            for g_order in g_orders:
                self.ser.write(g_order.encode())
            time.sleep(float(kwargs.get("wait_time", 2000)) / 1000)
            self.ser.write(deviate_order.encode())
            return 0
        elif kwargs.get("ignore_reset") or CORAL_TYPE < 5:
            for g_order in g_orders:
                self.ser.write(g_order.encode())
            return 0
        else:
            g_orders.append(deviate_order)
            for g_order in g_orders:
                self.ser.write(g_order.encode())
            return 0

    def recv(self, buffer_size=32):
        # print(self.ser.read(buffer_size))
        rev = self.ser.read(buffer_size).decode()
        if 'ok' in rev or 'unlock' in rev:
            return 0
        return -1

    def close(self):
        self.ser.close()
        return 0
