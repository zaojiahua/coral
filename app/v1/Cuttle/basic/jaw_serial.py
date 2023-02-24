import serial
import struct
import time

from binascii import *
import crcmod

from app.execption.outer.error_code.jaw import ActionNotAllow


class JawSerial:
    # 初始化指令和回复
    INIT_ORDER = "01 06 00 00 00 01 48 0A"
    INIT_REPLY = "010600000001480A"

    # 闭合指令前缀和回复(闭合范围0-50mm)
    CLOSURE_ORDER_PREFIX = "01 10 00 02 00 02 04"
    CLOSURE_ORDER_REPLY = "011000020002E008"

    # 设置夹持速度前缀和回复(速度范围 1-400mm/s)
    SET_SPEED_PREFIX = "01 10 00 04 00 02 04"
    SET_SPEED_REPLY = "0110000400020009"

    # 设置夹持电流(电流范围 0.1-0.5A)
    SET_ELECTRICITY_PREFIX = "01 10 00 06 00 02 04"
    SET_ELECTRICITY_REPLY = "011000060002A1C9"

    # 读取夹持状态(00 00表示到位，0:到位，1:运动中，2:夹持，3:掉落)
    READ_JAW_STATUS = "01 03 00 41 00 01 D4 1E"
    JAW_STATUS_REPLY = "0103020000B844"

    def __init__(self, baud_rate=115200, timeout=5):
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.ser = None
        self.jaw_com = None

    def connect(self, jaw_com):
        self.jaw_com = jaw_com
        self.ser = serial.Serial(self.jaw_com, self.baud_rate, timeout=self.timeout)
        return 0

    def set_jaw_to_spec_width(self, spec_width, action_prefix="CLOSURE_ORDER_PREFIX"):
        return self.send_order(jaw_obj.generate_order(target_data=spec_width, action_prefix=action_prefix))

    @staticmethod
    def float_to_hex(value):
        """
        将浮点数转化为二进制数
        :return: eg: float(48) -> 0x42400000
        """
        return hex(struct.unpack('<I', struct.pack('<f', float(value)))[0])

    @staticmethod
    def hex_to_str(hex_value):
        """
        将二进制数转为指定格式的字符串
        :param hex_value: eg:0x42400000
        :return: eg: 42 40 00 00
        """
        return " ".join([str(hex_value)[2:][i:i + 2] for i in range(0, len(str(hex_value)[2:]), 2)])

    @staticmethod
    def crc16Add(data):
        """
        生成crc16-modbus校验码
        """
        # print("data:",data)
        crc16 = crcmod.mkCrcFun(0x18005, rev=True, initCrc=0xFFFF, xorOut=0x0000)
        data = data.replace(" ", "")  # 消除空格
        data_crc_out = hex(crc16(unhexlify(data))).upper()
        str_list = list(data_crc_out)
        # print(str_list)
        if len(str_list) == 5:
            str_list.insert(2, '0')  # 位数不足补0，因为一般最少是5个
        crc_data = "".join(str_list)[2:].upper()  # 用""把数组的每一位结合起来  组成新的字符串
        # crc_data 低位在前，高位在后
        return crc_data[2:4] + " " + crc_data[:2]

    def generate_order(self, action_prefix="CLOSURE_ORDER_PREFIX", target_data=None):
        if action_prefix not in JawHandler.__dict__.keys():
            raise ActionNotAllow
        else:
            action_prefix = JawHandler.__dict__[action_prefix]
        if target_data:
            target_data_to_hex = self.hex_to_str((self.float_to_hex(target_data))).upper()
            crc_data = self.crc16Add(action_prefix + " " + target_data_to_hex)
            # print(target_data_to_hex)
            # print(crc_data)
            return action_prefix + " " + target_data_to_hex + " " + crc_data
        else:
            return action_prefix

    def send_order(self, action_order):
        print("生成的电爪指令：", action_order)
        send_data = bytes.fromhex(action_order)
        self.ser.write(send_data)
        return 0

    def recv_reply(self, action_type="CLOSURE_ORDER_REPLY", buffer_size=24):
        if action_type not in JawHandler.__dict__.keys():
            raise ActionNotAllow
        else:
            action_reply = JawHandler.__dict__[action_type]
            return_data = self.ser.read(buffer_size)
            str_return_data = str(return_data.hex()).upper()
            if action_reply == str_return_data:
                return 0
        return -1

    def close(self):
        self.ser.close()


if __name__ == '__main__':
    jaw_obj = JawHandler()
    jaw_obj.connect("com11")
    jaw_obj.set_jaw_to_spec_width(30)
    time.sleep(2)
    jaw_obj.close()
