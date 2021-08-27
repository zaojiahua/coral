from typing import List

from astra import models

from app.libs.log import setup_logger
from app.v1.Cuttle.boxSvc.request_sender import send_order
from redis_init import redis_client


class Box(models.Model):
    # 缓存木盒信息，用于coral内部运转，服务启动时从reef更新此表
    ip = models.CharField()
    port = models.IntegerField()
    init_status = models.BooleanField()  # true=on false=off
    total_number = models.IntegerField()
    method = models.CharField()
    type = models.CharField()

    def __init__(self, *args, **kwargs):
        super(Box, self).__init__(*args, **kwargs)
        self.logger = setup_logger(f'box{self.pk}', f'box-{self.pk}.log')

    def get_db(self):
        return redis_client

    @property
    def name(self):
        return self.pk

    @property
    def data(self):
        return {key: value._obtain() for key, value in self._astra_fields.items()}

    def update_attr(self, **kwargs):
        for key, value in self._astra_fields.items():
            if kwargs.get(key):
                setattr(self, key, kwargs.get(key))

    def verify_box(self, order_dict: dict) -> List:
        # 遍历验证单个木盒所有端口
        verified_list = []
        for port in range(1, self.total_number + 1):
            result = self.verify_single_port(order_dict, port)
            if result:
                verified_list.append(result)
        return verified_list

    def verify_single_port(self, order_dict: dict, port: int) -> str:
        # 验证单个端口
        num = "{:0>2d}".format(port)
        order = order_dict.get(num)
        response = send_order(self.ip, self.port, order, self.method)
        if self.judge_result(order, response):
            return f"{self.name}-{num}"

    @staticmethod
    def judge_result(request: str, response: str) -> bool:
        # 判断返回码是否与发送一致16位标识电量盒子，14位标识温度盒子
        if len(response) == 16:
            return True if request == response else False
        elif len(response) == 14:
            return True if 1 < int(response[6:10], 16) * 0.01 < 100 else False
        else:
            return False
