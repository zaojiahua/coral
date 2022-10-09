import time

from astra import models

from app.libs.extension.field import OwnerList, OwnerForeignKey
from app.libs.extension.model import BaseModel
from app.libs.log import setup_logger
from app.v1.djob import DJob
from app.config.setting import tboard_mapping


class DJobWorker(BaseModel):
    # 正常情况tboard 下发的djobManager 会被立即执行，tboard在执行过程会一直占用着device,djob_list提供了可以在device运行阶段插入djobManager的功能（内部插入）
    djob_list = OwnerList(to=DJob)
    retry = models.IntegerField()
    using_djob: DJob = OwnerForeignKey(to=DJob)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(f"{self.device_label}", f"{self.device_label}.log")

    @property
    def device_label(self):
        return self.pk

    def add(self, djob: DJob):
        # todo: 设置queue max length
        # if self.djob_list.llen() >= DJOB_QUEUE_MAX_LENGTH:
        #     return {"status": "djob_manager queue is full"}

        # 这里延迟1s添加，否则的话俩个djob开始的时间可能一样，导致rds推送不过去，因为rds需要保证同一台设备，同一个用例，开始时间三者唯一
        time.sleep(1)
        self.djob_list.lpush(djob)
        self.logger.info("(DJobWorker) add new DJob to wait list")

    def djob_process(self):
        # self.logger.info(f"{self.device_label} djobworker djob_process ")
        while len(self.djob_list) > 0:
            self.using_djob = self.djob_list.rpop()
            self.logger.info(f" DJobWorker ({self.pk}) pop a DJob"
                             f"({self.using_djob.job_label, self.using_djob.device_label})from wait list and put execute")

            self.using_djob.run_job_with_flow_execute_mode()
            # 执行完成，调用dut，推送djob到 DJobWorker
            self.callback()
            self.logger.info("callback finished ")

            self.using_djob.finish = True
            self.remove_job_from_tboard_mapping()
            self.using_djob.remove()
            self.logger.info("djob_process finished  now start next djob")

    def callback(self):
        if self.using_djob.tboard_id:
            from app.v1.tboard.model.dut import Dut
            Dut(pk=f"{self.device_label}_{self.using_djob.tboard_id}").start_dut()

    def remove_job_from_tboard_mapping(self):
        new_jobs = []
        # 接口形式没有随机，移除第一个找到的job即可
        for job_index, job in enumerate(tboard_mapping[self.using_djob.tboard_id]['jobs']):
            if job['job_label'] == self.using_djob.job_label and job_index == 0:
                print('移除job', job['job_label'])
                continue
            else:
                new_jobs.append(job)
        if len(new_jobs) == 0:
            del tboard_mapping[self.using_djob.tboard_id]
        else:
            tboard_mapping[self.using_djob.tboard_id]['jobs'] = new_jobs
        print('剩下的tboard_mapping')
        print(tboard_mapping)
