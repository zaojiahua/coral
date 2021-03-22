import os
import time

from app.config.ip import HOST_IP
from app.libs.ospathutil import makedirs_new_folder
from app.v1.djob.config.setting import BASE_PATH, RDS_DATA_PATH_NAME, DJOB_WORK_PATH_NAME
from app.v1.djob.model.device import DjobDevice


class DeviceViewModel:
    def __init__(self, device_label, flow_id, **kwargs):
        self.device_label = device_label

        self.device_name = None
        self.ip_address = None
        self.cabinet_id = None
        self.id = None
        self.tempport = None
        self.base_path = BASE_PATH.format(device_label=device_label, timestamp=time.time())

        self.rds_data_path = os.path.join(self.base_path, str(flow_id), RDS_DATA_PATH_NAME) + os.sep
        self.djob_work_path = os.path.join(self.base_path, str(flow_id), DJOB_WORK_PATH_NAME) + os.sep

    def to_model(self):
        makedirs_new_folder(self.rds_data_path)
        makedirs_new_folder(self.djob_work_path)  # if exist delete

        self._get_device_msg()

        # pk 不可以用device_label 因为后面生成的djob.device 和当前不是同一个资源对象
        device = DjobDevice(**self.__dict__)
        if self.tempport:
            device.temp_port.rpush(*self.tempport)
        return device

    def _get_device_msg(self):
        from app.v1.device_common.device_model import Device

        device = Device(pk=self.device_label)

        self.device_name = device.device_name
        self.ip_address = device.ip_address
        self.cabinet_id = HOST_IP.split(".")[-2]
        self.id = device.id
        self.tempport = device.temp_port_list.smembers()
