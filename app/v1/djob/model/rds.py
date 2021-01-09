from astra import models

from app.libs.extension.field import OwnerList
from app.libs.extension.model import BaseModel
from app.v1.eblock.model.eblock import Eblock


class RDS(BaseModel):
    error = models.CharField()
    job_flow_id = models.IntegerField()
    is_error = models.BooleanField()
    finish = models.BooleanField()
    error_msg = models.CharField()
    eblock_list = OwnerList(to=dict)
    last_node = models.CharField()
    is_use_result_unit = models.BooleanField()
    job_assessment_value = models.CharField()
