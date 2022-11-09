from astra import models

from app.config.setting import CORAL_TYPE
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
    # 该目录会跨多个job，不会删除
    share_path = models.CharField()
    device_label = models.CharField()
    temp_port = OwnerList()

    def save(self, action, attr=None, value=None):
        """
        删除时，会将当前djob的执行目录删除
        """
        if action == "pre_remove":
            if CORAL_TYPE <= 4:
                deal_dir_file(self.base_path)
