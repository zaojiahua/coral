import logging
import random
import time
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
    job_random_order = models.BooleanField()
    # 掉电关机使用的job
    special_job_msg = DictField()
    special_job_label = models.CharField()
    special_job_running = models.BooleanField()

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
        if ret is not None:
            return ret
        return ret

    @property
    def current_job_label(self):
        return self.get_job_label_by_index(self.current_job_index)

    @property
    def next_job_label(self):
        self.current_job_index += 1
        if self.job_random_order:
            if self.current_job_index % len(self.job_label_list) == 0:
                current_job_label_list = []
                while len(self.job_label_list) > 0:
                    current_job_label_list.append(self.job_label_list.lpop())
                random.shuffle(current_job_label_list)
                self.job_label_list.rpush(*current_job_label_list)
        return self.get_job_label_by_index(self.current_job_index)

    def start_dut(self):
        if self.exist():  # 停止dut 会在callback之前完成，停止dut会删除 dut instance,因此callback 不应进行
            from app.v1.device_common.device_model import Device, DeviceStatus
            device = Device(pk=self.device_label)
            if device.status == DeviceStatus.ERROR:
                self.remove_dut()
            else:
                current_job_label = self.next_job_label
                logger.info(f'current job index: {self.current_job_index}')
                if current_job_label is None:  # singal device's job finished
                    logger.info(f"dut ({self.pk}) finished and remove")
                    device_label = self.device_label
                    self.remove_dut()  # 完成后移除
                    # 这里设置状态为idle
                    self.update_device_status(device_label)
                else:
                    result_dict, *_ = self.send_djob()
                    self.djob_pk = result_dict.get("pk")

    def remove_dut(self):
        self.remove()
        self.check_tboard_finish()

    def update_device_status(self, device_label=None, status=None):
        from app.v1.device_common.device_model import Device, DeviceStatus
        device = Device(pk=device_label or self.device_label)
        # 这里设置状态为idle
        device.update_device_status(status or DeviceStatus.IDLE)

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

    # 代表是否是手动停止的
    def stop_dut(self, manual_stop=False):
        try:
            logger.debug(f"stop dut--------for {self.device_label}")
            self.stop_djob()
        except Exception as e:
            logger.error(f"stop djob {self.device_label, self.current_job_label} error :{e}")
        finally:
            # 这里设置状态为idle
            self.update_device_status(self.device_label)
            self.remove()
            # 手动停止的话，由reef自己判断，防止循环调用
            if not manual_stop:
                self.check_tboard_finish()
            logger.info(f"Delete dut device_label {self.device_label} ahead of time")

    def stop_djob(self):
        return remove_djob_inner(self.djob_pk)

    def send_djob(self):
        self.special_job_running = False
        json_data = {
            "device_label": self.device_label,
            "job_label": self.current_job_label.split(':')[0],
            "flow_execute_mode": self.job_msg[self.current_job_label]["flow_execute_mode"],
            "job_flows": self.job_msg[self.current_job_label]["job_flows"],
            'job_parameter': self.job_msg[self.current_job_label].get("job_parameter", {}),
            "source": "tboard",
            "tboard_id": self.parent.pk,
            "tboard_path": self.parent.tboard_path
        }
        logger.info(f"send insert djob, body：{json_data}")
        return insert_djob_inner(**json_data)

    # 加入特殊的掉电关机的job 临时方案
    def insert_special_djob(self):
        # 存在才执行，否则和普通的一样逻辑
        if self.special_job_label and not self.special_job_running:
            self.current_job_index -= 1
            logger.info(f'current job index: {self.current_job_index}')
            self.special_job_running = True
            # 先把正在执行的停止了
            print('停止正在执行的job。。。。。。。。。。')
            self.stop_djob()
            # 去掉所有的待机时间
            new_job_message = self.job_msg
            for job_label, msg in new_job_message.items():
                if 'job_parameter' in msg and 'standby_time' in msg['job_parameter']:
                    new_job_message[job_label]['job_parameter']['standby_time'] = 0
            self.job_msg = new_job_message
            # 等待5秒，上一个djob正在运行的unit可能还没有结束
            time.sleep(5)
            print('开启特殊的job。。。。。。。。。。。。。')
            json_data = {
                "device_label": self.device_label,
                "job_label": self.special_job_label,
                "flow_execute_mode": self.special_job_msg[self.special_job_label]["flow_execute_mode"],
                "job_flows": self.special_job_msg[self.special_job_label]["job_flows"],
                'job_parameter': self.special_job_msg[self.special_job_label].get("job_parameter", {}),
                "source": "tboard",
                "tboard_id": self.parent.pk,
                "tboard_path": self.parent.tboard_path,
                'not_push_rds': 1
            }
            logger.info(f"send insert djob, body：{json_data}")
            return insert_djob_inner(**json_data)

    # 获取用例执行到现在的待机时间
    def get_current_standby_time(self):
        total_standby_time = 0
        for job_index in range(self.current_job_index):
            job_label = self.get_job_label_by_index(self.current_job_index)
            msg = self.job_msg[job_label]
            if 'job_parameter' in msg and 'standby_time' in msg['job_parameter']:
                total_standby_time += msg['job_parameter']['standby_time']
        print('总的待机时长是：', total_standby_time)
        return total_standby_time
