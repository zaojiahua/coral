from concurrent.futures import as_completed, ThreadPoolExecutor

from astra import models

from app.libs.extension.field import OwnerList
from app.libs.extension.model import BaseModel
from app.v1.eblock.model.unit import Unit


class UnitList(BaseModel):
    key = models.CharField()
    units = OwnerList(to=Unit)

    load = ("units", "key")

    def process_unit_list(self, logger, handler, **kwargs):
        future_list = []
        for unit in self.units:
            executor = ThreadPoolExecutor(max_workers=30)
            future = executor.submit(unit.process_unit, logger, handler, **kwargs)
            future_list.append(future)
        for future in as_completed(future_list):
            future.result()  # 监控执行
