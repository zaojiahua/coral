import traceback

from astra import models

from app.execption.outer.error_code.imgtool import ClearBouncedOK
from app.libs.extension.field import OwnerList, OwnerForeignKey
from app.libs.extension.model import BaseModel
from app.libs.log import setup_logger
from app.v1.djob.config.setting import MAX_RETRY
from app.v1.djob.model.djob import DJob
from app.v1.djob.validators.djobSchema import DJobSchema


class DJobWorker(BaseModel):
    # 正常情况tboard 下发的djob 会被立即执行，tboard在执行过程会一直占用着device,djob_list提供了可以在device运行阶段插入djob的功能（内部插入）
    djob_list = OwnerList(to=DJob)
    retry = models.IntegerField()
    using_djob: DJob = OwnerForeignKey(to=DJob)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(f"djob-{self.device_label}", f"djob-{self.device_label}.log")

    @property
    def device_label(self):
        return self.pk

    def add(self, djob_obj: DJob):
        # todo: 设置queue max length
        # if self.djob_list.llen() >= DJOB_QUEUE_MAX_LENGTH:
        #     return {"status": "djob queue is full"}

        self.djob_list.lpush(djob_obj)
        self.logger.info("(DJobWorker) add new DJob to wait list")

    def djob_process(self):
        self.logger.info(f"{self.device_label} djobworker djob_process ")
        while len(self.djob_list) > 0:
            self.using_djob = self.djob_list.rpop()
            self.logger.info(f" DJobWorker ({self.pk}) pop a DJob "
                             f"({self.using_djob.job_label, self.using_djob.device_label})from wait list and put execute")

            while True:
                self.logger.info(f"{self.device_label} djob_process looping ")
                error = None
                error_traceback = None
                try:
                    self.run_single_djob()
                    break
                except Exception as ex:
                    self.logger.exception(f" run single djob exception: {ex}")
                    error_traceback = traceback.format_exc()
                    error = ex
                    if not isinstance(ex, ClearBouncedOK) or (
                            isinstance(ex, ClearBouncedOK) and self.retry >= MAX_RETRY):
                        break

                    # 清空当前djob产生的内容,重新执行
                    self.retry += 1
                    reserve_info = DJobSchema().dump(self.using_djob)
                    self.using_djob.remove()
                    self.using_djob = DJob(**reserve_info)

            try:
                if error:
                    self.using_djob.fake_rds(error, error_traceback)
            finally:
                self.retry = 0
                self.callback()
                self.using_djob.remove()  # delete using_djob
                self.using_djob = None


    def callback(self):
        if self.using_djob.tboard_id:
            from app.v1.tboard.model.dut import Dut
            Dut(pk=f"{self.device_label}_{self.using_djob.tboard_id}").start_dut()

    def run_single_djob(self):

        self.using_djob.prepare()

        self.logger.info(f"start for {self.device_label} {self.using_djob.job_label}")
        self.using_djob.execute()

        if self.using_djob.status is True:  # 执行完成

            self.logger.debug(
                f"djob exec center finished with {self.device_label} {self.using_djob.job_label}")

            self.using_djob.postprocess()

            self.logger.info(f"finished for {self.device_label} {self.using_djob.job_label}")
        else:
            self.logger.info(f"the djob {self.device_label} {self.using_djob.job_label} be stopped")

            self.using_djob.rds.remove()  # rds 需要手动删除


if __name__ == '__main__':
    d1 = DJobWorker(pk="112233")
    print(d1.using_djob)
    djob = DJob(pk="112233", source="2233eee")
    d1.using_djob = djob
    print(d1.using_djob)
    d1.using_djob.remove()
    print(d1.using_djob)
    # d1.djob_list.lpush(djob)
    # d1.djob_list.lpush(djob)
    # for dw in DJobWorker.djob_worker_list("fld"):
    #     dw.remove()
