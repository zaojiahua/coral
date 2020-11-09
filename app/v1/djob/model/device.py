from astra import models

from app.libs.extension.field import OwnerList
from app.libs.extension.model import BaseModel
from app.libs.ospathutil import deal_dir_file


class DjobDevice(BaseModel):
    device_name = models.CharField()
    ip_address = models.CharField()
    cabinet_id = models.CharField()
    id = models.CharField()
    base_path = models.CharField()
    rds_data_path = models.CharField()
    djob_work_path = models.CharField()
    device_label = models.CharField()
    temp_port = OwnerList()

    def save(self, action, attr=None, value=None):
        if action == "pre_remove":
            deal_dir_file(self.base_path)
