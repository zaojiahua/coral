from astra import models

from app.libs.extension.field import DictField
from app.libs.extension.model import BaseModel
from app.v1.djob.config.setting import START_TYPE


class Job(BaseModel):
    node_dict: dict = DictField()
    link_dict: dict = DictField()
    curr_node_key = models.CharField()
    # job_label = models.CharField()

    @property
    def start_name(self):
        return START_TYPE

    def get_node_dict_by_key(self, node_key):
        return self.node_dict.get(node_key)

    @property
    def start_key(self):
        """
        start_key并不是start对应得key
        而是start指向的第一个节点的key
        第一个节点默认为normal_block
        :return:
        """
        return self.link_dict[self.start_name]

    def get_start_node_dict(self):
        return self.get_node_dict_by_key(self.start_key)
