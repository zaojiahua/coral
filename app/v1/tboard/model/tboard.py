import datetime
import json
import logging
import time

from astra import models

from app.config.ip import HOST_IP, REEF_IP
from app.config.log import TBOARD_LOG_NAME
from app.config.url import tboard_id_url
from app.execption.outer.error import APIException
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.libs.ospathutil import deal_dir_file
from app.v1.djob.model.jobcacheproxy import JobCacheProxy
from app.v1.tboard.model.dut import Dut
from app.config.setting import email_addresses, default_email_address, REEF_DATE_TIME_FORMAT, CORAL_TYPE, \
    CORAL_TYPE_NAME
from app.libs.email_manager import EmailManager

logger = logging.getLogger(TBOARD_LOG_NAME)


class TBoard(BaseModel):
    board_name = models.CharHash()
    repeat_time = models.IntegerField()
    owner_label = models.CharField()
    create_level = models.CharField()
    dut_list = models.Set(to=Dut)  # 多个dut对象(dut: 一个device 对应多个jobSuite) set数据结构
    status = models.CharField()  # wait work stop
    tboard_path: str = models.CharField()

    @property
    def tboard_id(self):
        # 唯一标识
        return self.pk

    def save(self, action, attr=None, value=None):
        # 关联删除操作
        if action == "pre_remove":  # attr = 'pk', value = self.pk
            for dut in self.dut_list.smembers():
                dut.remove()

    def start_tboard(self, jobs):
        try:
            # job 本地资源同步
            job_cache_proxy = JobCacheProxy(jobs, self.tboard_path)
            sync_success = job_cache_proxy.sync()
            if not sync_success:
                raise Exception('资源同步失败')

            # 解压一次 解压过不会再次解压了
            for job in jobs:
                job_cache_proxy.unzip_job(job, self.tboard_path)

            for dut in self.dut_list.smembers():
                dut.start_dut()
        except Exception as e:
            logger.error(e)
            logger.exception(e)
            for dut in self.dut_list.smembers():
                dut.update_device_status()
            # 解压失败，停止 tboard，释放device
            self.send_tborad_finish()
            # 发送邮件，通知对应的人员
            email = EmailManager()
            email.send_email(email_addresses.get(int(REEF_IP.split(".")[-2]), default_email_address),
                             '任务发起失败，请检查！',
                             f'任务名称：{self.board_name}（{self.pk}）\n'
                             f'机柜：{REEF_IP.split(".")[-2]}号机 I\'M {HOST_IP.split(".")[-1]}'
                             f'（{CORAL_TYPE_NAME[CORAL_TYPE]}）\n'
                             f'{datetime.datetime.now().strftime(REEF_DATE_TIME_FORMAT)}')

    def send_tborad_finish(self):
        # 在多线程模式下，当前线程执行send_tborad_finish 会将tboard_id删除，tboard_id default 为0
        # 一直在Loop中跑djob的线程会从Loop中跳出也会调用访问send_tborad_finish，
        # 当 tboard_id = 0,就不会重复执行

        if self.tboard_id != 0:
            self.notify_tboard_finish(self.tboard_id)

            deal_dir_file(self.tboard_path)
            self.remove()
        else:
            logger.error(f"tboard({self.pk}) It has been deleted. cannot do this")

    @staticmethod
    def notify_tboard_finish(tboard_id):
        json_data = {
            "end_time": time.strftime('%Y_%m_%d_%H_%M_%S'),
            "cabinet_dict": json.dumps({HOST_IP.split(".")[-1]: 0})
        }
        while True:
            try:
                response = request(method="PUT", url=tboard_id_url.format(tboard_id), json=json_data)
                logger.info(f"end tboard response :{response}")
                break
            except APIException as e:
                if e.code not in [502, 504]:
                    raise e
