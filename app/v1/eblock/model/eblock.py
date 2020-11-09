import func_timeout
from astra import models

from app.execption.outer.error_code.eblock import EblockTimeOut, EblockEarlyStop
from app.libs.extension.field import OwnerList
from app.libs.extension.model import BaseModel
from app.libs.log import setup_logger
from app.v1.eblock.model.macro_replace import MacroHandler
from app.v1.eblock.model.unit import Unit
from app.v1.eblock.model.unitlist import UnitList


class Eblock(BaseModel):
    block_name = models.CharField()
    block_index = models.IntegerField()
    block_source = models.CharField()
    stop_flag = models.BooleanField()
    all_unit_list = OwnerList(to=UnitList)

    load = ("all_unit_list", "block_name", "pk")

    def __init__(self, pk=None, **kwargs):
        super().__init__(pk, **kwargs)

        load = kwargs.pop("load", False)
        if load:  # 需要加载其他属性时传入
            self.rds_path = kwargs["rds_path"]
            self.work_path = kwargs["work_path"]
            self.temp_port_list = kwargs["temp_port_list"]
            self.ip_address = kwargs["ip_address"]
            self.device_id = kwargs["device_id"]
            unit_list_index = 0
            for unit_list_dict in kwargs["unit_lists"]:
                unit_list_index += 1
                unit_list_instance = UnitList(key=unit_list_dict["key"])
                self.all_unit_list.rpush(unit_list_instance)
                for unit in unit_list_dict["unit_list"]:
                    unit_list_instance.units.rpush(
                        Unit(device_label=kwargs["device_id"], unit_list_index=unit_list_index, **unit))

            self.handler = MacroHandler(**kwargs)

            self.logger = setup_logger(f'eblock{self.device_id}', f'eblock-{self.device_id}.log')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return_val = True
        if exc_tb:
            if exc_type == func_timeout.exceptions.FunctionTimedOut:
                self.logger.warning("!!!---- unit timeout happen --- !!!!")
                raise EblockTimeOut
            else:
                self.logger.error(f"unknow exception happend:{exc_type},{exc_val}")
                return_val = False
        return return_val

    def start(self):
        self.logger.info(f"Eblock start--- for device :{self.device_id}")
        for units in self.all_unit_list:
            if self.stop_flag is True:
                self.logger.info(f"ready to stop eblock for device {self.device_id}")
                raise EblockEarlyStop()
            units.process_unit_list(self.logger, self.handler)
        self.logger.debug(f"unit list finished, result:{self.json()['all_unit_list']}")

    def stop(self):
        self.stop_flag = True
