import json
import math
import os
import random
import re
import time
from datetime import datetime
from typing import List

from astra import models

from app.config.setting import DEFAULT_DATE_TIME_FORMAT
from app.config.url import rds_create_or_update_url, rds_performance_pic
from app.execption.outer.error import APIException
from app.libs.extension.field import OwnerBooleanHash, OwnerDateTimeField, OwnerList, OwnerFloatField, OwnerForeignKey
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.djob.config.setting import SINGLE_SPLIT
from app.v1.djob.model.djobflow import DJobFlow
from app.libs.adbutil import get_room_version
from app.config.ip import ADB_TYPE
from app.config.setting import CORAL_TYPE
from app.libs.ospathutil import deal_dir_file

"""
inner job 只有一个 job flow
"""


class DJob(BaseModel):
    flow_execute_mode = models.CharField()
    job_flows_order = OwnerList(to=int)
    # 保存job flow的名字，rds中使用
    job_flows_name = OwnerList(to=str)

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
    start_point = models.IntegerField()  # 记录性能测试起点
    end_point = models.IntegerField()  # 记录性能测试终点
    lose_frame_point = models.IntegerField()  # 记录性能测试终点
    picture_count = models.IntegerField()  # 记录性能测试记录的总图片
    url_prefix = models.CharField()  # 记录性能测试存图的url前缀
    time_per_unit = OwnerFloatField()  # 记录性能测试存图单位时间
    rds_info_list = ["job_duration", "start_point", "end_point", "picture_count", "url_prefix", "time_per_unit",
                     "lose_frame_point"]
    # 特殊特征的rds提取和标识
    rds_feature_list = ['filter']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = None
        self.init_logger()

    def init_logger(self):
        if self.device_label:  # 如果Djob 中没有device_label attr ，写入总的 djob.log
            self.logger = setup_logger(f"{self.device_label}", f"{self.device_label}.log")

    def run_job_with_flow_execute_mode(self):

        self.start_time = datetime.now()

        if self.flow_execute_mode == SINGLE_SPLIT:
            for flow_index, flow_id in enumerate(self.job_flows_order):
                self.current_djob_flow = DJobFlow(flow_id=flow_id, device_label=self.device_label,
                                                  job_label=self.job_label, source=self.source,
                                                  tboard_path=self.tboard_path,
                                                  flow_name=self.job_flows_name[flow_index])
                self.djob_flow_list.rpush(self.current_djob_flow)

                self.current_djob_flow.run_single_flow()

                if self.stop:
                    self.logger.debug(f"the djob {self.device_label} {self.job_label} be stopped")
                    return

                if int(self.current_djob_flow.job_assessment_value) != 0:
                    # SingleSplit模式下，不成功则不继续执行
                    break
            self.analysis_result()
            self.postprocess()

    def analysis_result(self):

        self.job_assessment_value = self.djob_flow_list[-1].job_assessment_value

        # 特殊特征的rds提取和标识
        for djob_flow in self.djob_flow_list:
            for key in self.rds_feature_list:
                if getattr(djob_flow, key):
                    setattr(self, key, getattr(djob_flow, key))

        for djob_flow in self.djob_flow_list.lrange(-1, 0):
            for key in self.rds_info_list:
                # 将执行过程中需要写入rds的内容写入到djob对象
                if getattr(djob_flow, key):
                    setattr(self, key, getattr(djob_flow, key))

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

        # 特殊特征的rds提取和标识
        for key in self.rds_feature_list:
            if hasattr(self, key):
                json_data[key] = getattr(self, key)

        # 性能测试用例的测试时间的数据的保存
        for key in self.rds_info_list:
            if getattr(self, key):
                json_data[key] = getattr(self, key)

        if len(rds_result) != 0:
            app_info = []

            def process_unit(eblock):
                for unit_list in eblock.get('all_unit_list', []):
                    for unit in unit_list.get('units', []):
                        # 如果job执行成功，删除pictures
                        if int(self.job_assessment_value) == 0:
                            unit['pictures'] = []
                        # 写入APP INFO的信息
                        if unit.get('detail', {}).get('package_name') is not None:
                            app_info.append({'package_name': unit.get('detail').get('package_name'),
                                             'app_version': unit.get('detail').get('app_version')})

            for job_flow in rds_result:
                for eblock in job_flow.get('eblock_list', []):
                    if 'eblock_list' in eblock:
                        for inner_eblock in eblock.get('eblock_list', []):
                            process_unit(inner_eblock)
                    else:
                        process_unit(eblock)

            if len(app_info) > 0:
                json_data['app_info'] = json.dumps(app_info)

            json_data["rds_dict"] = json.dumps(rds_result)  # type  str

        from app.v1.device_common.device_model import Device
        device_cache = Device(self.device_label)
        if device_cache.is_exist():
            if math.floor(CORAL_TYPE) != 5:
                json_data["phone_model"] = device_cache.phone_model_name
                # rom version变化的时候，这里可能没有更新，所以进行实时的获取
                json_data["rom_version"] = device_cache.rom_version

                # 版本号有可能获取不到
                rom_version = get_room_version(
                    device_cache.ip_address if ADB_TYPE == 0 else (self.device_label.split("---")[-1]))
                if re.match(r'^[0-9a-zA-Z][0-9\.a-zA-Z]+[0-9a-zA-Z]$', rom_version) is not None:
                    json_data['rom_version_const'] = rom_version
                    self.logger.info(f'获取到的rom_version_const版本号是：{json_data["rom_version_const"]}')

        try:
            result = request(method="POST", json=json_data, url=rds_create_or_update_url)
            self.logger.info(f"ready to update rds<{result['id']}> info  to reef:{json_data}")
        except APIException as e:  # todo:会造成rds丢失，之后可以使用 mq 异步推送
            self.logger.error(
                f"the djob (device: {self.device_label}job: {self.job_label}) send api(rds_create_or_update) failed.{e}")
        else:
            self.push_file()  # 需要先创建rds，保证创建完成后上传关联数据并与之关联
            self.push_performance_file(result['id'])

    def push_file(self):
        json_data = {  # 与reef 通信异常忽略
            "device": self.device_label,
            "job": self.job_label,
            "start_time": self.start_time.strftime(DEFAULT_DATE_TIME_FORMAT),
            "tboard": self.tboard_id,
        }
        for djob_flow in self.djob_flow_list:
            djob_flow.push_log_and_pic(json_data, self.job_assessment_value)

    # 性能测试图片的推送。目前一个job中只能有一对性能测试的起点和终点，这些数据是在最外层的数据结构中定义的，不在job_flow中
    def push_performance_file(self, rds_id):
        # 存在数据的时候再操作
        work_path_start = self.url_prefix.find('path=')
        if work_path_start == -1:
            return
        work_path = self.url_prefix[work_path_start + len('path='):]
        if work_path:
            all_files = []

            for filename in os.listdir(work_path):
                file_path = os.path.join(work_path, filename)
                all_files.append(file_path)

            # 控制一次传输图片的数量
            step = 300
            for i in range(0, len(all_files), step):
                files = [('files', (os.path.split(file_path)[-1], open(file_path, 'rb'), 'file'))
                         for file_path in all_files[i: i + step]]

                print('性能测试图片上传中')
                try:
                    response = request(method="POST", url=rds_performance_pic, data={'rds': rds_id}, files=files)
                    # print('performance pic', response)
                except Exception as e:
                    print(e)
                    print('本次图片上传失败！')
                # 随机一个时间再上传，防止同一时间并发太多
                time.sleep(random.random())

            # 删除掉原始图片
            deal_dir_file(work_path)
