import datetime
import logging
import os
from concurrent.futures import ThreadPoolExecutor, wait

from app.config.setting import TBOARD_LOG_NAME, REEF_DATE_TIME_FORMAT
from app.v1.tboard.config.setting import TBOARD_PATH, MAX_CONCURRENT_NUMBER
from app.v1.tboard.model.dut import Dut
from app.v1.tboard.model.tboard import TBoard
from app.v1.tboard.validators.role import Role


class TBoardViewModel(object):

    def __init__(self, tboard_id, board_name, device_label_list,
                 jobs, repeat_time, owner_label, create_level):
        self.tboard_id = tboard_id
        self.board_name = board_name
        self.device_label_list = device_label_list
        self.jobs = jobs
        self.job_label_list = [job["job_label"] for job in jobs]
        self.repeat_time = repeat_time
        self.owner_label = owner_label
        self.create_level = create_level
        self.board_stamp = datetime.datetime.now().strftime(REEF_DATE_TIME_FORMAT)
        self.logger = logging.getLogger(TBOARD_LOG_NAME)

    # def keys(self):
    #     # https://blog.csdn.net/JENREY/article/details/87715651#4%E3%80%81%E6%9C%80%E7%BB%88%E7%9A%84%E4%BB%A3%E7%A0%81%E5%AE%9E%E7%8E%B0
    #     return ('board_name', 'device_label_list', 'job_label_list',
    #             'repeat_time', 'owner_label', 'board_stamp')
    #                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             
    # def __getitem__(self, item):
    #     return getattr(self, item)

    def add_dut(self, device_label, job_label_list, repeat_time, tboard_id):
        """
        生成一个任务集合 一个device 对应的多个job和运行次数
        """
        dut_obj = Dut(pk=f"{device_label}_{tboard_id}", parent_pk=tboard_id, stop_flag=False,
                      repeat_time=repeat_time, current_job_index=-1)

        dut_obj.job_label_list.rpush(*job_label_list)
        return dut_obj

    def add_dut_list(self, device_idle_list):
        """
        只运行idle 状态下的device
        :param device_idle_list:
        :return:
        """
        dut_obj_list = []
        for device_label in device_idle_list:
            dut_obj_list.append(self.add_dut(device_label, self.job_label_list, self.repeat_time, self.tboard_id))
        return dut_obj_list

    def create_tboard(self):
        usable_device_list = self.get_usable_device_list()
        if not usable_device_list:
            return -1

        tboard_path = os.path.join(TBOARD_PATH, str(self.tboard_id)) + os.sep

        # try:
        #     tboard_path = self.prepare_job_resource(self.tboard_id)
        # except Exception as e:
        #     self.logger.error(f"prepare job resource error --> {repr(e)}")
        #     deal_dir_file(tboard_path)
        #     request(method="PUT", url=tboard_id_url.format(self.tboard_id),
        #             json={
        #                 "end_time": time.strftime('%Y_%m_%d_%H_%M_%S'),
        #                 "cabinet_dict": json.dumps({HOST_IP.split(".")[-2]: 0})
        #             })
        #
        # self.logger.debug(f"prepare job resource finished --> for tboard{self.tboard_id}")
        tboard_obj = TBoard(pk=self.tboard_id, repeat_time=self.repeat_time, board_name=self.board_name,
                            owner_label=self.owner_label, status="work", create_level=self.create_level,
                            tboard_path=tboard_path)

        self.logger.info(
            f"create tboard tboard_id:{tboard_obj.tboard_id} own_label:{tboard_obj.owner_label}")

        dut_list = self.add_dut_list(usable_device_list)
        if dut_list:  # 保证dut被创建  (有空闲的device)
            tboard_obj.dut_list.sadd(*dut_list)  # set 用sadd
        return tboard_obj

    def get_usable_device_list(self):
        executor = ThreadPoolExecutor(MAX_CONCURRENT_NUMBER)
        all_task = []
        usable_device_list = []
        for idle_device in self.device_label_list:
            dut = Dut.first(device_label=idle_device)  # 因为不知道tboard_id 所以模糊查找，但是其实只有一个
            if dut is not None:
                tboard = getattr(dut, "parent", None)  # 极端条件下出现，在前面判断的dut还处于运行状态，但是在使用时已经运行完成并remove ,会导致parent获取异常
                create_level = tboard.create_level
                if tboard is None or create_level == "":  # 表明device被闲置下来了
                    usable_device_list.append(idle_device)
                # create 级别更高 可以停止上一个tboard 的dut，但是device status 不会改变，所以目前针对停止AI_TEST的tboard 中的dut
                elif Role[self.create_level].value > Role[create_level].value:
                    all_task.append(executor.submit(dut.stop_dut))
                    usable_device_list.append(idle_device)
            else:
                usable_device_list.append(idle_device)
        wait(all_task)  # block
        return usable_device_list

    # def create_tboard_path(self, tboard_id):
    #     tboard_path = os.path.join(TBOARD_PATH, str(tboard_id)) + os.sep
    #     if os.path.exists(tboard_path):
    #         deal_dir_file(tboard_path)
    #     os.makedirs(tboard_path)
    #     self.logger.debug(f"make a dir for tboard num:{tboard_id}")
    #     return tboard_path
    #
    # def prepare_job_resource(self, tboard_id):
    #     tboard_path = self.create_tboard_path(tboard_id)
    #
    #     for job_label in self.job_label_list:
    #         job_path = os.path.join(tboard_path, job_label)
    #         if not os.path.exists(job_path):
    #             os.makedirs(job_path)
    #         upload_job_res_file(job_path, job_label)
    #     return tboard_path
