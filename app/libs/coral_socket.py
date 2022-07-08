import socket

import func_timeout

from app.libs.func_tools import async_timeout

# 封装的socket通信，主要用来与继电器和温感箱通信，只有1型柜会用到

class CoralSocket(socket.socket):
    """
     coral 内部与继电器/温感通信使用，实现了with表达式，用以区别多种异常
    """

    def __init__(self, port=20000):
        super(CoralSocket, self).__init__()
        self.hardware_port = port
        self.code_type = "ISO-8859-1"

    def connect(self, ip_address):
        return super(CoralSocket, self).connect((ip_address, self.hardware_port))

    def send(self, data, flags=None):
        data_16 = ""
        for x in range(0, len(data), 2):
            data_16 += chr(int(data[x:x + 2], 16))
        return super(CoralSocket, self).send(data_16.encode(self.code_type))

    @async_timeout(6)
    def recv(self, buffersize=50, flags=None):
        response = super(CoralSocket, self).recv(buffersize)
        reply_temp = ""
        for i in response.decode(self.code_type):
            reply_temp += "0x%02x" % ord(i)
        reply_temp = reply_temp[2:]
        mb = ""
        while reply_temp:
            mb += reply_temp[0:2]
            reply_temp = reply_temp[4:]
        return mb

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
            raise exception when return 10063, catch exception when need retry
        """
        if not self._closed:
            self.close()
        if exc_tb:  # ConnectionAbortedError
            if "No route to host" in str(exc_val):
                return False
            if TimeoutError == exc_type:
                return False
            if "already connected" in str(exc_val):
                return True
            from concurrent.futures import TimeoutError as TimeoutErrorThread
            if TimeoutErrorThread == exc_type:
                return True
            if func_timeout.exceptions.FunctionTimedOut == exc_type:
                return True
            else:
                return False
        else:
            return True
