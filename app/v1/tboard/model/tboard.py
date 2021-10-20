import json
import logging
import os
import time
import zipfile

from astra import models

from app.config.ip import HOST_IP
from app.config.log import TBOARD_LOG_NAME
from app.config.setting import JOB_SYN_RESOURCE_DIR
from app.config.url import tboard_id_url
from app.execption.outer.error import APIException
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.libs.ospathutil import deal_dir_file
from app.v1.djob.model.jobcacheproxy import JobCacheProxy
from app.v1.tboard.model.dut import Dut

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
            job_cache_proxy = JobCacheProxy(jobs)
            job_cache_proxy.sync()
            # 从项目同级目录job_resource下获取幸运的job zipfile解压到运行目录 self.tboard_path
            for job in jobs:
                job_msg_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job['job_label']}.zip")
                with zipfile.ZipFile(job_msg_name, 'r') as zip_ref:
                    zip_ref.extractall(os.path.join(self.tboard_path, job["job_label"]))
                if job.get("inner_job", []):
                    for inner_job in job["inner_job"]:
                        job_msg_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{inner_job['job_label']}.zip")
                        with zipfile.ZipFile(job_msg_name, 'r') as zip_ref:
                            zip_ref.extractall(os.path.join(self.tboard_path, inner_job["job_label"]))

            for dut in self.dut_list.smembers():
                dut.start_dut()
        except Exception as e:
            logger.error(e)
            logger.exception(e)
            # 解压失败，停止 tboard，释放device
            self.send_tborad_finish()

    def send_tborad_finish(self):
        # 在多线程模式下，当前线程执行send_tborad_finish 会将tboard_id删除，tboard_id default 为0
        # 一直在Loop中跑djob的线程会从Loop中跳出也会调用访问send_tborad_finish，
        # 当 tboard_id = 0,就不会重复执行

        if self.tboard_id != 0:
            json_data = {
                "end_time": time.strftime('%Y_%m_%d_%H_%M_%S'),
                "cabinet_dict": json.dumps({HOST_IP.split(".")[-1]: 0})
            }  # datetime 格式
            while True:
                try:
                    response = request(method="PUT", url=tboard_id_url.format(self.tboard_id), json=json_data)
                    logger.info(f"end tboard response :{response}")
                    break
                except APIException as e:
                    if e.code not in [502, 504]:
                        raise e

            deal_dir_file(self.tboard_path)
            self.remove()

        else:
            logger.error(f"tboard({self.pk}) It has been deleted. cannot do this")
