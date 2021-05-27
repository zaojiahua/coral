from astra import models

from app.libs.extension.field import OwnerList, OwnerForeignKey
from app.libs.extension.model import BaseModel
from app.libs.log import setup_logger
from app.v1.djob import DJob


class DJobWorker(BaseModel):
    # 正常情况tboard 下发的djobManager 会被立即执行，tboard在执行过程会一直占用着device,djob_list提供了可以在device运行阶段插入djobManager的功能（内部插入）
    djob_list = OwnerList(to=DJob)
    retry = models.IntegerField()
    using_djob: DJob = OwnerForeignKey(to=DJob)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(f"djob-{self.device_label}", f"djob-{self.device_label}.log")

    @property
    def device_label(self):
        return self.pk

    def add(self, djob: DJob):
        # todo: 设置queue max length
        # if self.djob_list.llen() >= DJOB_QUEUE_MAX_LENGTH:
        #     return {"status": "djob_manager queue is full"}

        self.djob_list.lpush(djob)
        self.logger.info("(DJobWorker) add new DJob to wait list")

    def djob_process(self):
        self.logger.info(f"{self.device_label} djobworker djob_process ")
        while len(self.djob_list) > 0:
            self.using_djob = self.djob_list.rpop()
            self.logger.info(f" DJobWorker ({self.pk}) pop a DJob"
                             f"({self.using_djob.job_label, self.using_djob.device_label})from wait list and put execute")

            self.using_djob.run_job_with_flow_execute_mode()
            # 执行完成，调用dut，推送djob到 DJobWorker
            self.callback()

            self.using_djob.remove()

    def callback(self):
        if self.using_djob.tboard_id:
            from app.v1.tboard.model.dut import Dut
            Dut(pk=f"{self.device_label}_{self.using_djob.tboard_id}").start_dut()
