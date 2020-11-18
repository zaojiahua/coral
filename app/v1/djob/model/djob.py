import json
import os
from datetime import datetime
from shutil import copyfile

from astra import models

from app.config.setting import DEFAULT_DATE_TIME_FORMAT
from app.config.url import rds_create_or_update_url, upload_rds_screen_shot_url, \
    upload_rds_log_file_url
from app.execption.outer.error import APIException
from app.execption.outer.error_code.djob import JobExecBodyException, JobExecUnknownException, JobMaxRetryCycleException
from app.execption.outer.error_code.eblock import EblockEarlyStop
from app.libs.extension.field import OwnerBooleanHash, OwnerDateTimeField, DictField, OwnerList, OwnerForeignKey, \
    OwnerFloatField
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.djob.config.setting import NORMAL_TYPE, SWITCH_TYPE, END_TYPE, FAILED_TYPE, ADBC_TYPE, TEMPER_TYPE, \
    IMGTOOL_TYPE, SUCCESS_TYPE, SUCCESS, FAILED, INNER_DJOB_TYPE, DJOB, ERROR_STACK, COMPLEX_TYPE, ERROR_FILE_DIR
from app.v1.djob.model.device import DjobDevice
from app.v1.djob.model.job import Job
from app.v1.djob.model.joblink import JobLink
from app.v1.djob.model.jobnode import JobNode
from app.v1.djob.model.rds import RDS
from app.v1.djob.viewModel.device import DeviceViewModel
from app.v1.djob.viewModel.job import JobViewModel
from app.v1.eblock.model.eblock import Eblock
from app.v1.eblock.views.eblock import insert_eblock, stop_eblock


class DJob(BaseModel):
    job: Job = OwnerForeignKey(to=Job)
    device: DjobDevice = OwnerForeignKey(to=DjobDevice)
    start_time = OwnerDateTimeField()
    end_time = OwnerDateTimeField()
    stop_flag = OwnerBooleanHash()
    source = models.CharField()
    device_label = models.CharField()
    job_label = models.CharField()
    tboard_path = models.CharField()
    tboard_id = models.IntegerField()
    rds_id = models.IntegerField()
    status = OwnerBooleanHash()  # False 执行未完成  True 执行完成
    exec_node_index = models.IntegerField()  # 当前执行的node 节点的index
    recent_adb_wrong_code = models.IntegerField()  # 获取当前block 最后一条错误的adbc 指令的code default 为 0 表示没有错误
    recent_img_res_list = OwnerList(
        to=int)  # 栈结构rpush,rpop 记录当前 normal 中img_tool结果，recent_img_res_list的结果会被switch or end 消耗
    recent_img_rpop_list = OwnerList(to=int)  # 栈结构 rpush,rpop  记录 被switch消耗的 recent_img_res_list的结果，用于end 结果收集
    switch_node_dict = DictField()  # 记录每一个switch_block被执行的次数
    recent_img_msg_dict = DictField()  # 记录当前block img_tool输出的信息
    temp_dict = DictField()  # 记录整个job执行过程的温度
    job_assessment_value = models.CharField()  # 记录rds结果
    job_duration = OwnerFloatField()  # 记录rds结果
    rds = OwnerForeignKey(to=RDS)  # 记录rds 详细结果,用于分析
    assist_device_serial_number = models.IntegerField()  # 记录僚机信息default 为 0 目前支持序列号 【1，2，3】
    inner_job_list = OwnerList(to="app.v1.djob.model.djob.DJob")
    inner_job_index = models.IntegerField()  # 当前执行的inner job 的 index

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = None
        self.init_logger()

    @property
    def temper_changes(self):

        if len(self.temp_dict) >= 2:
            temp_list = list(self.temp_dict.values())
            return max(temp_list) - min(temp_list)

        return None

    def prepare(self):
        self.start_time = datetime.now()

        self.create_rds()  # 关联rds

        job_vm = JobViewModel(self.job_label, self.tboard_path,
                              assist_device_serial_number=self.assist_device_serial_number)
        self.job = job_vm.to_model()
        device_vm = DeviceViewModel(device_label=self.device_label)
        self.device = device_vm.to_model()

    def init_logger(self):
        if self.device_label:  # 如果Djob 中没有device_label attr ，写入总的 djob.log
            self.logger = setup_logger(f"djob-{self.device_label}", f"djob-{self.device_label}.log")

    def create_rds(self):
        self.rds = RDS(tboard=self.tboard_id)

    def execute(self):
        node_key = self.job.start_key
        node_dict = self.job.get_start_node_dict()

        while True:
            self.logger.info(
                f"the djob (device: {self.device_label}job: {self.job_label}) exec"
                f" node_key :{node_key} , node_dict :{node_dict}")

            if self.stop_flag:
                return

            next_node_dict = self._execute_node(node_key, node_dict)
            if next_node_dict is None:  # djob 执行出口
                break
            job_link_instance = JobLink(node_key, next_node_dict)
            # todo: exec link operation
            node_key = next_node_dict.get("nextNode")
            node_dict = self.job.get_node_dict_by_key(node_key)
        # job_assessment_value默认值"",
        # 当用户指定unit结果作为最终结果会将result赋值给job_assessment_value，作为最终结果值
        if self.job_assessment_value == "":
            self.job_assessment_value = self.computed_result()
        self.rds.job_assessment_value = self.job_assessment_value
        self.rds.finish = True
        self.end_time = datetime.now()
        self.status = True

    def computed_result(self):
        last_node = self.rds.last_node
        if last_node == END_TYPE:
            return self.djob_result()

        elif last_node == SUCCESS_TYPE:
            return SUCCESS

        elif last_node == FAILED_TYPE:
            return FAILED
        else:
            raise JobExecBodyException(description=f"job {self.job_label} exec failed:  last exec node is {last_node}")

    def postprocess(self):
        """
        结果处理
        :return:
        """
        self.push_rds_result()

    def _execute_node(self, node_key, node_dict):
        job_node = JobNode(node_key, node_dict)

        self.rds.last_node = job_node.node_type

        if job_node.node_type == NORMAL_TYPE:
            self.exec_node_index += 1
            self._execute_normal(job_node)
            next_node_dict = self.job.link_dict[node_key]

        elif job_node.node_type == INNER_DJOB_TYPE:
            self.exec_node_index += 1
            self._execute_inner_djob(job_node)
            next_node_dict = self.job.link_dict[node_key]

        elif job_node.node_type == SWITCH_TYPE:
            next_node_dict = self._execute_switch(job_node)

        elif job_node.node_type in [END_TYPE, SUCCESS_TYPE, FAILED_TYPE]:
            return
        else:
            raise JobExecBodyException(description=f"invalid node type :{job_node.node_type}")
        return next_node_dict

    def djob_result(self):
        """
        recent_img_rpop_list,recent_img_res_list 均为栈结构

        djob执行结果计算逻辑:
        获取recent_img_rpop_list 最近结果(index is -1),
        recent_img_rpop_list为空 从recent_img_res_list 获取最近结果(index is -1)
        recent_img_res_list 为空表明djob不产生结果, result 赋值 -32

        result 为 1表示imgtool比对失败，会查看 recent_adb_wrong_code，
        若recent_adb_wrong_code 为空 为 result 赋值 1
        若 recent_adb_wrong_code有值，则将其作为可能导致djob 执行错误的结果依据，赋值给 result
        """
        result = self.recent_img_rpop_list[-1] if len(self.recent_img_rpop_list) else self.recent_img_res_list[
            -1] if len(self.recent_img_res_list) else -32

        if result == 1 and self.recent_adb_wrong_code:  # 如果为 0,说明没有错误,因此 result = 1
            result = self.recent_adb_wrong_code

        return int(result)

    def _execute_inner_djob(self, job_node):
        djob = DJob(device_label=self.device_label, job_label=job_node.job_label, source=DJOB, tboard_id=self.tboard_id,
                    tboard_path=self.tboard_path, inner_job_index=self.exec_node_index)
        self.inner_job_list.rpush(djob)
        if job_node.assist_device_serial_number is not None:  # assist_device_serial_number表明运行的是哪一台僚机
            djob.assist_device_serial_number = job_node.assist_device_serial_number
        djob.prepare()
        djob.execute()
        self.recent_img_res_list = None
        self.recent_img_rpop_list = None
        self.recent_img_res_list.rpush(int(djob.job_assessment_value))
        self.rds.eblock_list.rpush(djob.rds.json())
        # djob.remove()

    def _execute_normal(self, job_node):

        eblock: Eblock = self._insert_exec_block(job_node)

        if eblock:
            self._eblock_return_data_parse(eblock)
            self.rds.eblock_list.rpush(eblock.json())
            eblock.remove()

    def _insert_exec_block(self, job_node):
        """
        eblock 会判断当前device是否正在执行其他block，
        如果处于执行状态会返回error,Djob会尝试三次
        :param job_node:
        :return:
        """

        for retry in range(3):
            try:
                return self._get_eblock_return(job_node)
            except EblockEarlyStop:  # eblock执行被终止
                return

    def _get_eblock_return(self, job_node):

        eblock = Eblock()

        # self.rds.eblock_list.rpush(eblock)

        json_data = {
            "pk": eblock.pk,
            "block_index": self.exec_node_index,
            "device_id": self.device_label,
            "block_source": "Djob",
            "work_path": self.device.djob_work_path,
            "rds_path": self.device.rds_data_path,
            "temp_port_list": self.device.temp_port.lrange(0, -1),
            "ip_address": self.device.ip_address,
            **job_node.exec_node_dict
        }

        return insert_eblock(json_data)

    def _execute_switch(self, job_node):
        switch_node_dict = self.switch_node_dict

        if switch_node_dict.setdefault(job_node.node_key, 0) >= 3:
            # 如果任务执行循环是else分支会造成死循环，需要避免,因此采用向上抛出异常
            raise JobMaxRetryCycleException()
        else:
            switch_node_dict[job_node.node_key] += 1

            if len(self.recent_img_res_list):
                score = self.recent_img_res_list.rpop()  # 最左边的最新
                self.recent_img_rpop_list.rpush(score)  # 最右边的最新被遗弃的
                if score == 1 and self.recent_adb_wrong_code:
                    score = self.recent_adb_wrong_code

                score = str(score)
            else:
                score = "else"
        next_switch_dict = self.job.link_dict.get(job_node.node_key)
        next_node_dict = next_switch_dict[score] if score in next_switch_dict.keys() else next_switch_dict["else"]

        self.switch_node_dict = switch_node_dict
        return next_node_dict

    def _eblock_return_data_parse(self, eblock):
        """
            IMGTOOL result: 0 成功   -1 未知异常 1 失败
            ADBC result: 0 成功   < 0 失败
            TEMPER  返回温度信息

        :return:
        """

        self.recent_img_res_list = None  # 每一个block 产生的结果会覆盖recent_img_res_list
        self.recent_img_rpop_list = None

        for unit_list in eblock.all_unit_list:
            for unit in unit_list.units:
                # 存在却没有结果表明未执行完成或未执行,
                # 因为创建eblock时就会创建unit,但是只有执行完的unit才由result
                result = unit.detail.get("result", None)
                if self.job_duration == float(0):  # 获取第一个time(并不是用例执行时间,是性能用例测量的时间)
                    self.job_duration = unit.detail.get("time", float(0.0))
                result = unit.detail.get("result", None)  # 存在没有结果表明未执行完成
                if unit.execModName == ADBC_TYPE:
                    if result is not None and result < 0:
                        self.recent_adb_wrong_code = result

                elif unit.execModName == IMGTOOL_TYPE or unit.execModName == COMPLEX_TYPE:
                    if result is not None:
                        if unit.finalResult:  # 是否将当前unit结果作为最终结果
                            self.job_assessment_value = result
                        self.recent_img_res_list.rpush(result)
                        self.recent_img_msg_dict = {**self.recent_img_msg_dict, **unit.detail}

                elif unit.execModName == TEMPER_TYPE:
                    self.temp_dict = {**self.temp_dict, **unit.detail}

    def inform_eblock_stop(self):
        # 当前运行的eblock为rds.eblock_list最右边的eblock

        stop_eblock(self.rds.eblock_list[-1].pk)

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
                DEFAULT_DATE_TIME_FORMAT) if self.end_time else datetime.now().strftime(DEFAULT_DATE_TIME_FORMAT),
            "temper_changes": self.temper_changes  # reef 没有temper_changes 这个参数
        }

        rds_result = self.rds.json() if self.rds else {}  # 可能存在rds未被创建就发生异常，因此需要判断
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
            json_data["job_assessment_value"] = self.job_assessment_value
            self.push_log_and_pic(self, **json_data)  # 需要先创建rds，保证创建完成后上传关联数据并与之关联

    def push_log_and_pic(self, instance, device, job, start_time, tboard, job_assessment_value, **kwargs):
        """
        :param instance: djob instance
        :param device:
        :param job:
        :param start_time:
        :param tboard:
        :param kwargs:
        :return:
        """
        if instance.device is None:  # device prepare error 导致device 未初始化
            return

            # 与reef 通信异常忽略
        json_data = {
            "device": device,
            "job": job,
            "start_time": start_time,
            "tboard": tboard,
        }

        for file_name in os.listdir(instance.device.rds_data_path):

            file_path = os.path.join(instance.device.rds_data_path, file_name)

            if os.path.getsize(file_path):
                if int(job_assessment_value) != 0:  # 针对正确的结果不推送文件
                    if file_name.endswith((".png", ".jpg")):
                        json_data["file_name"] = file_name

                        pic = open(file_path, "rb")

                        try:
                            request(method="POST", url=upload_rds_screen_shot_url, data=json_data,
                                    files={"rds_screen_shot": pic})
                        except APIException as e:
                            instance.logger.error(f"{file_path} push failed: {e}")
                            copyfile(file_path, os.path.join(ERROR_FILE_DIR, file_name))

                        pic.close()

                if file_name.endswith((".txt", ".log", ".json")):
                    json_data["file_name"] = file_name
                    log = open(file_path, "rb")
                    try:
                        request(method="POST", url=upload_rds_log_file_url, data=json_data,
                                files={"log_file": log})
                    except APIException as e:
                        instance.logger.error(f"{file_path} push failed: {e}")
                        copyfile(file_path, os.path.join(ERROR_FILE_DIR, file_name))
                    log.close()

        def rds_file_rename(path, prefix):
            for _file_name in os.listdir(path):
                _file_path = os.path.join(path, _file_name)
                os.rename(_file_path, os.path.join(path, f"({prefix}_{_file_name[1:]}"))

        for djob_instance in instance.inner_job_list:
            rds_file_rename(djob_instance.device.rds_data_path, djob_instance.inner_job_index)
            self.push_log_and_pic(djob_instance, device, job, start_time, tboard, job_assessment_value, **kwargs)

    def fake_rds(self, e, error_traceback):
        print(error_traceback)

        if isinstance(e, APIException):
            self.logger.error(
                f"the djob device_label:{self.device_label}  job_label: {self.job_label} execute exception "
                f"because {e.description} from {e.__class__}")

            self.job_assessment_value = e.error_code

        else:
            # 针对这种非常规异常,记录到特定位置提供分析
            setup_logger(f"tboard({self.tboard_id})_rds",
                         f"tboard_{self.tboard_id}_rds_error.log").exception(f"Djob exec failed : {error_traceback}")

            self.logger.error(
                f"the djob (device: {self.device_label}job: {self.job_label}) exec unknown failure,error:{e}")

            self.job_assessment_value = JobExecUnknownException.error_code

        self.add_error_msg(e, error_traceback)

        self.push_rds_result()

    def add_error_msg(self, error, error_traceback):
        self.rds.error = error.__class__.__name__
        self.rds.finish = True
        self.rds.tboard = self.tboard_id
        self.rds.job_assessment_value = self.job_assessment_value
        self.rds.is_error = True
        if int(self.job_assessment_value) in ERROR_STACK:  # 内容过大，针对未知异常进行详细信息的保存
            self.rds.error_msg = error_traceback


if __name__ == "__main__":
    a = {
        1: {"ADBC": {"result": [0]}},
        2: {"ADBC": {"result": [0]}},
        3: {"ADBC": {"result": [0, 1]}, "TEMPER": {"3_temp": 25.2}},
        4: {"IMGTOOL": {"timeConsume": 12.87, "result": [0]}}

    }

    print(os.path.getsize("E:\\1111.txt"))
