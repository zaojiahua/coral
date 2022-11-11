import os
import re
import traceback
import zipfile
from datetime import datetime
from shutil import copyfile

from astra import models

from app.config.setting import JOB_SYN_RESOURCE_DIR, BUGREPORT
from app.config.url import upload_rds_screen_shot_url, upload_rds_log_file_url, upload_rds_zip_file_url
from app.execption.outer.error import APIException
from app.execption.outer.error_code.djob import JobExecBodyException, JobExecUnknownException, \
    InnerJobNotAssociated, DeviceStatusError
from app.execption.outer.error_code.eblock import EblockEarlyStop
from app.libs.extension.field import OwnerBooleanHash, OwnerDateTimeField, DictField, OwnerList, OwnerForeignKey, \
    OwnerFloatField
from app.libs.extension.model import BaseModel
from app.libs.http_client import request, request_file
from app.libs.log import setup_logger
from app.libs.ospathutil import file_rename_from_path, deal_dir_file
from app.v1.djob.config.setting import NORMAL_TYPE, SWITCH_TYPE, END_TYPE, FAILED_TYPE, ADBC_TYPE, TEMPER_TYPE, \
    IMGTOOL_TYPE, SUCCESS_TYPE, SUCCESS, FAILED, INNER_DJOB_TYPE, DJOB, COMPLEX_TYPE, ERROR_FILE_DIR, ABNORMAL_TYPE, \
    ABNORMAL, TERMINATE_TYPE, TERMINATE
from app.v1.djob.model.device import DjobDevice
from app.v1.djob.model.job import Job
from app.v1.djob.model.joblink import JobLink
from app.v1.djob.model.jobnode import JobNode
from app.v1.djob.model.rds import RDS
from app.v1.djob.viewModel.device import DeviceViewModel
from app.v1.djob.viewModel.job import JobViewModel
from app.v1.eblock.model.eblock import Eblock
from app.v1.eblock.views.eblock import insert_eblock, stop_eblock
from app.execption.outer.error_code.imgtool import DetectNoResponse
from app.v1.eblock.model.macro_replace import BlockTimes


class DJobFlow(BaseModel):
    # 初始化传入
    source = models.CharField()  # tboard 下发的, djob 下发的（目前djob下发的是inner job）
    device_label = models.CharField()
    job_label = models.CharField()
    tboard_path = models.CharField()
    flow_id = models.IntegerField()
    # 记录父级flow_id 为0代表没有父级
    parent_flow_id = models.IntegerField()
    flow_name = models.CharField()
    job_parameter = DictField()

    job: Job = OwnerForeignKey(to=Job)
    device: DjobDevice = OwnerForeignKey(to=DjobDevice)
    start_time = OwnerDateTimeField()
    end_time = OwnerDateTimeField()
    stop_flag = OwnerBooleanHash()

    status = OwnerBooleanHash()  # False 执行未完成  True 执行完成
    exec_node_index = models.IntegerField()  # 当前执行的node 节点的index
    recent_adb_wrong_code = models.IntegerField()  # 获取当前block 最后一条错误的adbc 指令的code default 为 0 表示没有错误
    block_recent_adb_wrong_code = models.IntegerField()
    recent_img_res_list = OwnerList(
        to=int)  # 栈结构rpush,rpop 记录当前 normal 中img_tool结果，recent_img_res_list的结果会被switch or end 消耗
    recent_img_rpop_list = OwnerList(to=int)  # 栈结构 rpush,rpop  记录 被switch消耗的 recent_img_res_list的结果，用于end 结果收集
    switch_node_dict = DictField()  # 记录每一个switch_block被执行的次数
    recent_img_msg_dict = DictField()  # 记录当前block img_tool输出的信息
    temp_dict = DictField()  # 记录整个job执行过程的温度
    job_assessment_value = models.CharField()  # 记录rds结果
    job_duration = OwnerFloatField()  # 记录rds结果，获取第一个time(并不是用例执行时间,是性能用例测量的时间)
    start_point = models.IntegerField()  # 记录性能测试起点
    end_point = models.IntegerField()  # 记录性能测试终点
    picture_count = models.IntegerField()  # 记录性能测试记录的总图片
    lose_frame_point = models.IntegerField()  # 记录性能测试记录的总图片
    url_prefix = models.CharField()  # 记录性能测试存图的url前缀
    time_per_unit = OwnerFloatField()  # 记录性能测试存图单位
    frame_data = OwnerList(to=dict)
    start_method = models.IntegerField()
    end_method = models.IntegerField()
    set_fps = OwnerFloatField()
    fps = OwnerFloatField()
    set_shot_time = OwnerFloatField()
    rds = OwnerForeignKey(to=RDS)  # 记录rds 详细结果,用于分析
    assist_device_serial_number = models.IntegerField()  # 记录僚机信息default 为 0 目前支持序列号 【1，2，3】
    inner_job_list = OwnerList(to="app.v1.djob.model.djobflow.DJobFlow")
    inner_job_index = models.IntegerField()  # 当前执行的inner job 的 index
    current_eblock = OwnerForeignKey(to=Eblock)  # 当前正在执行的eblock
    # 当前的jobflow当做inner job的时候（也就是是其他job_flow的一个block），需要在rds中存储这个字段
    block_name_as_inner_job = models.CharField()
    filter = models.CharField()  # 发生了严重错误 比如某些APP没有响应

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = None
        self.init_logger()
        # 记录switch node的引用
        self.switch_node_ref = {}

        # 修改推送到rds的文件名时候的用
        self.inner_job_prefix_name = f"(inner_{self.inner_job_index})"
        self.flow_prefix_name = f"(flow_{self.parent_flow_id or self.flow_id})"

    def init_logger(self):
        if self.device_label:  # 如果Djob 中没有device_label attr ，写入总的 djob.log
            self.logger = setup_logger(f"{self.device_label}", f"{self.device_label}.log")

    @property
    def temper_changes(self):
        """
        todo:现在还未对该内容记录，占留之后有需求再做

        用于记录job flow执行过程中的温度差

        reef 没有temper_changes 这个参数

        :return:
        """
        if len(self.temp_dict) >= 2:
            temp_list = list(self.temp_dict.values())
            return max(temp_list) - min(temp_list)

        return None

    def run_single_flow(self):
        try:
            self.prepare()

            self.execute()
        except EblockEarlyStop:
            self.logger.info(f" djobflow ({self.device_label} {self.job_label} {self.flow_id}) be stopped")
        except DetectNoResponse:
            # 没有响应，设置特殊的结果以及字段
            self.job_assessment_value = 1
            self.filter = 'serious'
            self.rds.job_assessment_value = self.job_assessment_value
            self.rds.finish = True
            self.rds.flow_name = self.flow_name
        except DeviceStatusError as ex:
            self.fake_rds(ex, '')
        except Exception as ex:
            self.logger.exception(f" run single djob exception: {ex}")
            error_traceback = traceback.format_exc()
            self.fake_rds(ex, error_traceback)

    def prepare(self):
        if self.source == DJOB:  # djob 表明为innerjob, 只有一个job flow 且未传,需要自己获取
            if not os.path.exists(os.path.join(self.tboard_path, self.job_label)):
                self.download_fix(self.tboard_path, self.job_label)
            if not os.path.exists(os.path.join(self.tboard_path, self.job_label)):
                raise InnerJobNotAssociated
            self.flow_id = int(os.listdir(os.path.join(self.tboard_path, self.job_label))[0])

        self.create_rds()  # 关联rds

        job_vm = JobViewModel(self.job_label, self.tboard_path,
                              assist_device_serial_number=self.assist_device_serial_number,
                              flow_id=self.flow_id)
        self.job = job_vm.to_model()

        device_vm = DeviceViewModel(device_label=self.device_label, flow_id=self.flow_id)
        self.device = device_vm.to_model()

    @staticmethod
    def download_fix(tboard_path, job_label):
        try:
            url = f"/media/job_res_file_export/{job_label}.zip"
            job_msg_temp_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}.zip")
            file_content = request_file(url, timeout=100.0)
            with open(job_msg_temp_name, "wb") as code:
                code.write(file_content.content)
            with zipfile.ZipFile(job_msg_temp_name, 'r') as zip_ref:
                zip_ref.extractall(os.path.join(tboard_path, job_label))
        except Exception:
            raise InnerJobNotAssociated

    def create_rds(self):
        self.rds = RDS(job_flow_id=self.flow_id)

    def execute(self):
        self.start_time = datetime.now()

        node_key = self.job.start_key

        node_dict = self.job.get_start_node_dict()

        try:
            while True:
                self.logger.info(
                    f"the djob (device: {self.device_label}job: {self.job_label}) exec"
                    f" node_key :{node_key}")

                if self.stop_flag:
                    raise EblockEarlyStop

                # 运行次数动态定义
                max_time = node_dict['maxTime'] if node_dict and node_dict["nodeType"] == SWITCH_TYPE else ''
                if BlockTimes in str(max_time):
                    # 里边的数字代表如果服务器没有传入动态参数，则默认的次数
                    max_time = re.findall(f"{BlockTimes}(.*?)>", max_time)
                    if len(max_time) > 0:
                        max_time = max_time[0]
                    else:
                        max_time = 1
                    node_dict['maxTime'] = self.job_parameter['time'] - 1 if 'time' in self.job_parameter else max_time
                    print(self.job_parameter, 'job_parameter')

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
            else:  # 已经存在，说明结果unit事先声明设置了
                self.rds.is_use_result_unit = True
            self.rds.job_assessment_value = self.job_assessment_value
        finally:
            self.rds.finish = True
            self.rds.flow_name = self.flow_name
            self.rds.block_name = self.block_name_as_inner_job
            self.end_time = datetime.now()
            self.status = True
            # 写入循环执行的次数
            self.log_switch_time()

    def log_switch_time(self):
        # 写入循环执行的次数
        for key, execute_time in self.switch_node_dict.items():
            # 执行次数大于1代表是循环
            if int(execute_time) > 1:
                job_node = self.switch_node_ref[key]
                self.rds.switch_times.rpush(
                    {'time': execute_time, 'name': job_node.block_name, 'max_time': job_node.max_time})

    def computed_result(self):
        last_node = self.rds.last_node
        if last_node == END_TYPE:
            return self.djob_result()

        elif last_node == SUCCESS_TYPE:
            return SUCCESS

        elif last_node == FAILED_TYPE:
            return FAILED
        elif last_node == ABNORMAL_TYPE:
            result_code = self.djob_result()
            result_code = ABNORMAL if result_code in [0, 1] else result_code
            return result_code
        elif last_node == TERMINATE_TYPE:
            return TERMINATE
        else:
            raise JobExecBodyException(description=f"job {self.job_label} exec failed:  last exec node is {last_node}")

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

        elif job_node.node_type in [END_TYPE, SUCCESS_TYPE, FAILED_TYPE, ABNORMAL_TYPE, TERMINATE_TYPE]:
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

        if result == 1 and self.recent_adb_wrong_code:  # recent_adb_wrong_code 如果为 0,说明没有错误,因此 result = 1
            result = self.recent_adb_wrong_code

        return int(result)

    def _execute_inner_djob(self, job_node):
        # inner_job 只有一个 job flow 所以 flow_id 无所谓 设置成 0
        dJob_flow = DJobFlow(device_label=self.device_label, job_label=job_node.job_label,
                             source=DJOB,
                             tboard_path=self.tboard_path,
                             inner_job_index=self.exec_node_index,
                             block_name_as_inner_job=job_node.block_name,
                             parent_flow_id=self.flow_id)
        self.inner_job_list.rpush(dJob_flow)
        if job_node.assist_device_serial_number is not None:  # assist_device_serial_number表明运行的是哪一台僚机
            dJob_flow.assist_device_serial_number = job_node.assist_device_serial_number
        try:
            dJob_flow.prepare()
            dJob_flow.execute()
            self.recent_img_res_list = None
            self.recent_img_rpop_list = None
            self.block_recent_adb_wrong_code = 0
            self.recent_img_res_list.rpush(int(dJob_flow.job_assessment_value))
        finally:
            self.rds.eblock_list.rpush(dJob_flow.rds.json())

    def _execute_normal(self, job_node):

        try:
            self._insert_exec_block(job_node)
        finally:
            if self.current_eblock:
                self._eblock_return_data_parse(self.current_eblock)
                block_rds = self.current_eblock.json()
                if self.recent_img_res_list and len(self.recent_img_res_list) > 0:
                    score = self._get_score(False)
                    block_rds['value'] = int(score)
                self.rds.eblock_list.rpush(block_rds)
                self.current_eblock.remove()

    def _insert_exec_block(self, job_node):
        """
        eblock 会判断当前device是否正在执行其他block，
        如果处于执行状态会返回error,Djob会尝试三次
        :param job_node:
        :return:
        """

        for retry in range(3):
            return self._get_eblock_return(job_node)

    def _get_eblock_return(self, job_node):

        self.current_eblock = Eblock()

        # self.rds.eblock_list.rpush(eblock)
        json_data = {
            "pk": self.current_eblock.pk,
            "block_index": self.exec_node_index,
            "device_id": self.device_label,
            "block_source": "Djob",
            "work_path": self.device.djob_work_path,
            "rds_path": self.device.rds_data_path,
            'share_path': self.device.share_path,
            "temp_port_list": self.device.temp_port.lrange(0, -1),
            "ip_address": self.device.ip_address,
            **job_node.exec_node_dict,
            'job_parameter': self.job_parameter
        }

        return insert_eblock(json_data)

    def _execute_switch(self, job_node):
        # 记录引用
        if self.switch_node_ref.get(job_node.node_key, None) is None:
            self.switch_node_ref[job_node.node_key] = job_node

        switch_node_dict = self.switch_node_dict

        if switch_node_dict.setdefault(job_node.node_key, 0) >= int(job_node.max_time or 0):
            # 如果任务执行循环是else分支会造成死循环，需要避免,因此采用向上抛出异常
            # raise JobMaxRetryCycleException()
            # 超过最大的循环次数，走else分支
            score = 'else'
        else:
            switch_node_dict[job_node.node_key] += 1

            score = self._get_score()
        next_switch_dict = self.job.link_dict.get(job_node.node_key)
        next_node_dict = next_switch_dict[score] if score in next_switch_dict.keys() else next_switch_dict["else"]

        self.switch_node_dict = switch_node_dict
        return next_node_dict

    # 获取block的执行结果，根据该结果执行Switch分支
    def _get_score(self, is_switch=True):
        if len(self.recent_img_res_list):
            if is_switch:
                score = self.recent_img_res_list.rpop()  # 最左边的最新
                self.recent_img_rpop_list.rpush(score)  # 最右边的最新被遗弃的
            else:
                score = self.recent_img_res_list[-1]

            if score == 1 and self.block_recent_adb_wrong_code:
                score = self.block_recent_adb_wrong_code
            score = str(score)
        else:
            score = "else"

        self.logger.info(f" switch 最后的计算结果是： {score}) .........")
        return score

    def _eblock_return_data_parse(self, eblock):
        """
            IMGTOOL result: 0 成功   -1 未知异常 1 失败
            ADBC result: 0 成功   < 0 失败
            TEMPER  返回温度信息

        :return:
        """
        rds_info_list = ["job_duration", "start_point", "end_point", "picture_count", "url_prefix", "time_per_unit",
                         "lose_frame_point", 'start_method', 'end_method', 'set_fps', 'set_shot_time', 'fps']
        self.recent_img_res_list = None  # 每一个block 产生的结果会覆盖recent_img_res_list
        self.recent_img_rpop_list = None
        self.block_recent_adb_wrong_code = 0

        for unit_list in eblock.all_unit_list:
            for unit in unit_list.units:

                # 修改rds中保存的图片名称
                new_picture = []
                picture = unit.pictures.rpop()
                while picture is not None:
                    if self.source == DJOB:
                        picture = self.inner_job_prefix_name + '_' + picture
                    picture = self.flow_prefix_name + '_' + picture
                    new_picture.append(picture)
                    picture = unit.pictures.rpop()
                for pictures in new_picture:
                    unit.pictures.lpush(pictures)

                # 存在却没有结果表明未执行完成或未执行,
                # 因为创建eblock时就会创建unit,但是只有执行完的unit才由result
                for key in rds_info_list:
                    if unit.detail.get(key):
                        setattr(self, key, unit.detail.get(key))

                # 保存每一帧的数据
                if unit.detail.get('frame_data'):
                    for frame_info in unit.detail.get('frame_data'):
                        self.frame_data.lpush(frame_info)

                result = unit.detail.get("result", None)  # 存在没有结果表明未执行完成
                if unit.execModName == ADBC_TYPE:
                    if result is not None:
                        if unit.finalResult:  # 是否将当前unit结果作为最终结果
                            self.job_assessment_value = result
                    if result is not None and result < 0:
                        self.recent_adb_wrong_code = result
                        self.block_recent_adb_wrong_code = result

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

    def fake_rds(self, e, error_traceback):
        """
        生产异常结果，并记录异常信息
        :param e:
        :param error_traceback:
        :return:
        """
        if isinstance(e, APIException):
            self.logger.error(
                f"the djob device_label:{self.device_label}  job_label: {self.job_label} execute exception "
                f"because {e.description} from {e.__class__}")

            self.job_assessment_value = e.error_code
        else:
            self.logger.error(
                f"the djob (device: {self.device_label}job: {self.job_label}) exec unknown failure,error:{e}")

            self.job_assessment_value = JobExecUnknownException.error_code

        self.add_error_msg(e, error_traceback)

    def add_error_msg(self, error, error_traceback):
        self.rds.error = error.__class__.__name__
        self.rds.finish = True
        self.rds.job_assessment_value = self.job_assessment_value
        self.rds.is_error = True
        self.rds.error_msg = error_traceback
        # 写入循环执行的次数
        self.log_switch_time()

    def push_log_and_pic(self, base_data: dict, job_assessment_value, **kwargs):
        """
        :param base_data: 请求关联rds的基础数据
        :param job_assessment_value: djob 得到的结果
        :param kwargs:
        :return:
        """
        flow_id = kwargs.pop("flow_id", self.flow_id)
        if self.device is None:  # device prepare error 导致device 未初始化
            return
        if self.source == DJOB:
            file_rename_from_path(self.device.rds_data_path, self.inner_job_prefix_name)

        file_rename_from_path(self.device.rds_data_path, self.flow_prefix_name)

        for file_name in os.listdir(self.device.rds_data_path):
            file_path = os.path.join(self.device.rds_data_path, file_name)

            if os.path.getsize(file_path):
                if int(job_assessment_value) != 0:  # 针对正确的结果不推送文件
                    if file_name.endswith((".png", ".jpg")):
                        self._send_file(base_data, file_name, file_path, upload_rds_screen_shot_url, "rds_screen_shot")
                    elif file_name.endswith(".zip"):
                        self._send_file(base_data, file_name, file_path, upload_rds_log_file_url, "log_file")
                if file_name.endswith((".txt", ".log", ".json")):
                    self._send_file(base_data, file_name, file_path, upload_rds_log_file_url, "log_file")
                # 针对bugreport的特殊逻辑
                elif BUGREPORT in file_name and int(job_assessment_value) == 0:
                    name_frag = file_name[:-4].split('_')
                    if len(name_frag) > 0 and name_frag[-1].isdigit():
                        self._send_file(base_data, file_name, file_path, upload_rds_log_file_url, "log_file")

        for djob_instance in self.inner_job_list:
            # inner job的 依赖文件上传
            djob_instance.push_log_and_pic(base_data, job_assessment_value, flow_id=flow_id)

        # 将共享目录下的文件进行上传，上传完以后需要删除文件，否则下次还会上传
        for file_name in os.listdir(self.device.share_path):
            file_path = os.path.join(self.device.share_path, file_name)
            if os.path.getsize(file_path):
                self._send_file(base_data, file_name, file_path, upload_rds_log_file_url, "log_file")
            deal_dir_file(file_path)

    def _send_file(self, base_data, file_name, file_path, url, key):
        base_data["file_name"] = file_name
        file = open(file_path, "rb")
        try:
            request(method="POST", url=url, data=base_data, files={key: file})
        except APIException as e:
            self.logger.error(f"{file_path} push failed: {e}")
            copyfile(file_path, os.path.join(ERROR_FILE_DIR, file_name))
        file.close()

    def stop_flow(self):
        self.stop_flag = True
        # todo:关联的eblock 或者inner job停止
        if self.rds.last_node == INNER_DJOB_TYPE:
            self.inner_job_list[-1].stop_flow()
        else:
            stop_eblock(self.current_eblock.pk)


if __name__ == "__main__":
    a = {
        1: {"ADBC": {"result": [0]}},
        2: {"ADBC": {"result": [0]}},
        3: {"ADBC": {"result": [0, 1]}, "TEMPER": {"3_temp": 25.2}},
        4: {"IMGTOOL": {"timeConsume": 12.87, "result": [0]}}

    }

    print(os.path.getsize("E:\\1111.txt"))
