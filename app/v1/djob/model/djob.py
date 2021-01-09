import json
from datetime import datetime
from typing import List

from astra import models

from app.config.setting import DEFAULT_DATE_TIME_FORMAT
from app.config.url import rds_create_or_update_url
from app.execption.outer.error import APIException
from app.libs.extension.field import OwnerBooleanHash, OwnerDateTimeField, OwnerList, OwnerFloatField, OwnerForeignKey
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.djob.model.djobflow import DJobFlow

"""
inner job 只有一个 job flow
"""


class DJob(BaseModel):
    flow_execute_mode = models.CharField()
    job_flows_order = OwnerList(to=int)

    current_djob_flow: DJobFlow = OwnerForeignKey(to=DJobFlow)
    djob_flow_list: List[DJobFlow] = OwnerList(to=DJobFlow)

    start_time = OwnerDateTimeField()
    end_time = OwnerDateTimeField()
    stop_flag = OwnerBooleanHash()

    source = models.CharField()
    device_label = models.CharField()
    job_label = models.CharField()
    tboard_path = models.CharField()
    tboard_id = models.IntegerField()

    stop = models.BooleanField()  # default False 未停止  True  手动停止

    job_assessment_value = models.CharField()  # 记录rds结果
    job_duration = OwnerFloatField()  # 记录性能测试用例性能数据（运行时间）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = None
        self.init_logger()

    def init_logger(self):
        if self.device_label:  # 如果Djob 中没有device_label attr ，写入总的 djob.log
            self.logger = setup_logger(f"djob-{self.device_label}", f"djob-{self.device_label}.log")

    def run_job_with_flow_execute_mode(self):

        self.start_time = datetime.now()

        if self.flow_execute_mode == "SingleSplit":
            for flow_id in self.job_flows_order:
                self.current_djob_flow = DJobFlow(flow_id=flow_id, device_label=self.device_label,
                                                  job_label=self.job_label, source=self.source,
                                                  tboard_path=self.tboard_path)
                self.djob_flow_list.rpush(self.current_djob_flow)

                self.current_djob_flow.run_single_flow()

                if self.stop:
                    self.logger.debug(f"the djob {self.device_label} {self.job_label} be stopped")
                    return

                if int(self.current_djob_flow.job_assessment_value) != 0:
                    break
            self.analysis_result()
            self.postprocess()

    def analysis_result(self):
        self.job_assessment_value = self.djob_flow_list[-1].job_assessment_value
        for djob_flow in self.djob_flow_list.lrange(-1, 0):
            if djob_flow.job_duration != float(0):
                self.job_duration = djob_flow.job_duration
                break

    def postprocess(self):
        """
        结果处理
        :return:
        """
        if self.stop is False:

            self.logger.debug(
                f"djob exec center finished with {self.device_label} {self.job_label}")

            self.push_rds_result()

            self.logger.debug(f"finished for {self.device_label} {self.job_label}")
        else:
            self.logger.debug(f"the djob {self.device_label} {self.job_label} be stopped")

    def stop_djob(self):
        # 当前运行的eblock为rds.eblock_list最右边的eblock
        self.stop = True
        self.current_djob_flow.stop_flow()

    def push_rds_result(self):
        """
            向reef 推送rds结果
        """
        json_data = {
            "device": self.device_label,
            "job": self.job_label,
            "start_time": self.start_time.strftime(DEFAULT_DATE_TIME_FORMAT),
            "tboard": self.tboard_id,
            "job_assessment_value": self.job_assessment_value,
            "end_time": self.end_time.strftime(
                DEFAULT_DATE_TIME_FORMAT) if self.end_time else datetime.now().strftime(DEFAULT_DATE_TIME_FORMAT)
        }
        rds_result = []
        for djob_flow in self.djob_flow_list:
            rds_result.append(djob_flow.rds.json() if djob_flow.rds else {})
        # 性能测试用例的测试时间的数据的保存
        if self.job_duration != float(0):
            json_data["job_duration"] = self.job_duration
        if len(rds_result) != 0:
            json_data["rds_dict"] = json.dumps(rds_result)  # type  str
        from app.v1.device_common.device_model import Device

        device_cache = Device(self.device_label)
        if device_cache.is_exist():
            json_data["phone_model"] = device_cache.phone_model_name
            json_data["rom_version"] = device_cache.rom_version

        try:
            result = request(method="POST", json=json_data, url=rds_create_or_update_url)
            self.logger.info(f"ready to update rds<{result['id']}> info  to reef:{json_data}")
        except APIException as e:  # todo:会造成rds丢失，之后可以使用mq 异步推送
            self.logger.error(
                f"the djob (device: {self.device_label}job: {self.job_label}) send api(rds_create_or_update) failed.{e}")
        else:
            self.push_file()  # 需要先创建rds，保证创建完成后上传关联数据并与之关联

    def push_file(self):
        json_data = {  # 与reef 通信异常忽略
            "device": self.device_label,
            "job": self.job_label,
            "start_time": self.start_time.strftime(DEFAULT_DATE_TIME_FORMAT),
            "tboard": self.tboard_id,
        }
        for djob_flow in self.djob_flow_list:
            djob_flow.push_log_and_pic(json_data, self.job_assessment_value)
