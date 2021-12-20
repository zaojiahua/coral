import logging
from threading import Lock

from astra import models

from app.config.setting import TBOARD_LOG_NAME
from app.execption.outer.error import APIException
from app.libs.extension.field import OwnerBooleanHash, OwnerList, DictField
from app.libs.extension.model import BaseModel
from app.v1.djob.views.insert_djob import insert_djob_inner
from app.v1.djob.views.remove_djob import remove_djob_inner

lock = Lock()

logger = logging.getLogger(TBOARD_LOG_NAME)


class Dut(BaseModel):
    """
    # 多个dut对象(dut: 一个device 对应多个job 和轮询次数)
    """
    stop_flag = OwnerBooleanHash()
    job_label_list = OwnerList()
    job_msg = DictField()
    repeat_time: int = models.IntegerField()
    djob_pk = models.CharField()
    device_label = models.CharField()
    current_job_index: int = models.IntegerField()
    model = "app.v1.tboard.model.tboard.TBoard"

    def save(self, action, attr=None, value=None):
        if action == "post_remove":  # attr = 'pk', value = self.pk
            if hasattr(self, "parent"):
                self.parent.dut_list.srem(value)

    @property
    def total_job_number(self):
        return self.repeat_time * len(self.job_label_list)

    # @property
    # def device_label(self):  # pk  (device_label)_(tboard_id)
    #     return self.pk.split("_")[0]

    def get_job_label_by_index(self, job_index):
        ret = None
        job_list_len = len(self.job_label_list)
        if job_index < self.total_job_number and job_list_len > 0:
            ret = self.job_label_list[job_index % job_list_len]
        return ret

    @property
    def current_job_label(self):
        return self.get_job_label_by_index(self.current_job_index)

    @property
    def next_job_label(self):
        self.current_job_index += 1
        # self.current_job_index_incr()
        return self.get_job_label_by_index(self.current_job_index)

    def start_dut(self):
        if self.exist():  # 停止dut 会在callback之前完成，停止dut会删除 dut instance,因此callback 不应进行
            current_job_label = self.next_job_label
            if current_job_label is None:  # singal device's job finished
                logger.info(f"dut ({self.pk}) finished and remove")
                self.remove_dut()  # 完成后移除
            else:
                result_dict, *_ = self.send_djob()
                self.djob_pk = result_dict.get("pk")

    def remove_dut(self):
        self.remove()
        self.check_tboard_finish()

    def check_tboard_finish(self):
        try:
            lock.acquire(timeout=20.0)
            tboard = getattr(self, "parent", None)
            if tboard is None:
                logger.error(f"dut {self.device_label} not belonging to any tboard")
                return
            if len(tboard.dut_list) == 0:  # tborad finished
                logger.info(f"Tborad {tboard.tboard_id} finish")
                tboard.send_tborad_finish()
                logger.info(f"Tborad {tboard.tboard_id} send reef success")
        except Exception as e:
            if isinstance(e, APIException):
                logger.error(f"Tborad {tboard.tboard_id} send tborad finish APIException:{e.description}")
            else:
                logger.error(f"Tborad {tboard.tboard_id} send tborad finish unknown Exception:{repr(e)}")
        finally:
            lock.release()

    def stop_dut(self):
        try:
            logger.debug(f"stop dut--------for {self.device_label}")
            self.stop_djob()
        except Exception as e:
            logger.error(f"stop djob {self.device_label, self.current_job_label} error :{e}")
        finally:
            self.remove()
            self.check_tboard_finish()
            logger.info(f"Delete dut device_label {self.device_label} ahead of time")

    def stop_djob(self):
        return remove_djob_inner(self.djob_pk)

    def send_djob(self):
        json_data = {
            "device_label": self.device_label,
            "job_label": self.current_job_label,
            "flow_execute_mode": self.job_msg[self.current_job_label]["flow_execute_mode"],
            "job_flows": self.job_msg[self.current_job_label]["job_flows"],
            "source": "tboard",
            "tboard_id": self.parent.pk,
            "tboard_path": self.parent.tboard_path
        }
        logger.info(f"send insert djob, body：{json_data}")
        return insert_djob_inner(**json_data)
