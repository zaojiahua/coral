import os
import shutil
from functools import lru_cache
from astra import models
from func_timeout import func_set_timeout

from app.config.ip import ADB_TYPE
from app.config.url import device_url
from app.execption.outer.error_code.djob import AssistDeviceOrderError, AssistDeviceNotFind
from app.execption.outer.error_code.eblock import EblockCannotFindFile
from app.libs.extension.field import DictField
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.eblock.config.leadin import PROCESSER_LIST
from app.v1.eblock.config.setting import DEFAULT_TIMEOUT
from app.v1.eblock.model.macro_replace import MacroHandler


def get_assist_device_ident(device_label, assist_device_serial_number):
    """
    获取主机下的僚机信息并返回,不存在则返回None
    assist_device_serial_number 值为1，2，3

    :param device_label: str
    :param assist_device_serial_number: int
    :return:
    """
    if assist_device_serial_number not in [1, 2, 3]:
        raise AssistDeviceOrderError()
    device_detail_msg = request(
        url=device_url, params={
            "fields":
                "subsidiarydevice.id,subsidiarydevice.serial_number,subsidiarydevice.ip_address,subsidiarydevice.order",
            "device_label": device_label
        },
        filter_unique_key=True
    )
    for subsidiary_device in device_detail_msg["subsidiarydevice"]:
        if subsidiary_device["order"] == assist_device_serial_number:
            connect_number = subsidiary_device.get("ip_address") + ":5555" if ADB_TYPE == 0 else subsidiary_device.get(
                "serial_number")
            return connect_number
    raise AssistDeviceNotFind(
        description="Job used the no. 1 assist device of the primary device, but the primary device did not")


class Unit(BaseModel):
    """
    ADBC sample:
    {
        'execCmdDict':
             {
                 'bkupCmdList': [],
                 'execCmdList': [
                     {'type': 'noChange', 'content': '<3adbcTool> shell input keyevent 4'},
                     {'type': 'noChange', 'content': '<3adbcTool> shell input keyevent 4'},
                     {'type': 'noChange', 'content': '<3adbcTool> shell input keyevent 4'},
                     {'type': 'noChange', 'content': '<3adbcTool> shell input keyevent 3'},
                     {'type': 'noChange', 'content': '<3adbcTool> shell input keyevent 3'},
                     {'type': 'noChange', 'content': '<3adbcTool> shell input keyevent 3'}
                 ],
                 'exptResList': []
             },
         'execModName': 'ADBC',
         'jobUnitName': '回到桌面',
         'unitDescription': '回到桌面',
    }

    other:
    {
         'execCmdDict': {
             'xyShift': {
                 'type': 'uxInput', 'content': 'Tmach0  Tmach-40 ',
                 'meaning': '输入偏移量x和y（向上/向左为负值）'
             },
             'inputImgFile': {
                 'type': 'inputPicture',
                 'content': '<blkOutPath>Tmachsnap1-1.png ',
                 'meaning': '输入传入图片的文件名，其通常来自于之前的一个截图Unit'
             },
             'requiredWords': {
                 'type': 'uxInput', 'content': 'Tmach设置 ',
                 'meaning': '输入要识别的文字'
             }
         },
         'execModName': 'IMGTOOL',
         'jobUnitName': '文字识别并点击',
         'functionName': 'get_ocr_position_and_point',
         'unitDescription': '根据文字查找并点击对应位置'
         'assistDevice':'辅助设备编号'
         'finalResult':True
     }
    """
    key = models.CharField()  # unit 的唯一标识会重因此不可写入到pk中
    timeout = models.IntegerField()  # unit 的唯一标识会重因此不可写入到pk中
    detail = DictField()  # 用于存储结果
    jobUnitName = models.CharField()
    execCmdDict = DictField()
    execModName = models.CharField()  # 类型
    functionName = models.CharField()
    device_label = models.CharField()
    assistDevice = models.IntegerField()
    finalResult = models.BooleanField()
    ocrChoice = models.IntegerField()
    unit_list_index = models.IntegerField()

    load = ("detail", "key", "execModName", "jobUnitName", "finalResult")

    def process_unit(self, logger, handler: MacroHandler, **kwargs):
        assist_device_ident = get_assist_device_ident(self.device_label,
                                                      self.assistDevice) if self.assistDevice else None

        @func_set_timeout(timeout=self.timeout if self.timeout else DEFAULT_TIMEOUT)
        def _inner_func():

            save_list = []
            cmd_dict: dict = self.execCmdDict
            if 'ADBC' == self.execModName:
                # only want content， get ride of meaning&type
                cmd_list = [i.get("content") for i in cmd_dict.get("execCmdList")]
                repalced_cmd_list = []
                for cmd in cmd_list:
                    try:
                        replaced_cmd, save_file = handler.replace(cmd, assist_device_ident=assist_device_ident)
                    except EblockCannotFindFile as ex:  # 解释失败,不记录结果
                        logger.error(f"unit replace fail {ex}")
                        return
                    if save_file:
                        save_list.append(save_file)
                    if replaced_cmd:
                        repalced_cmd_list.append(replaced_cmd)
                logger.debug("----replace adb macro finished in eblock--(adbc)--")
                cmd_dict["execCmdList"] = repalced_cmd_list

                sending_data = {"device_label": self.device_label, "ip_address": handler.ip_address, **cmd_dict}
                if kwargs.pop("test_running", False):
                    sending_data["test_running"] = True

                if assist_device_ident is None:
                    from app.v1.device_common.device_model import Device
                    if Device(pk=self.device_label).has_arm and cmd_dict.get("have_second_choice", 0) == 1:
                        target = PROCESSER_LIST[1]
                    elif Device(pk=self.device_label).has_camera and cmd_dict.get("have_second_choice", 0) == 2:
                        target = PROCESSER_LIST[2]
                    elif Device(pk=self.device_label).has_rotate_arm and cmd_dict.get("have_second_choice", 0) == 3:
                        target = PROCESSER_LIST[1]
                    else:
                        target = PROCESSER_LIST[0]
                else:
                    target = PROCESSER_LIST[0]

            else:
                for key, value in cmd_dict.items():
                    try:
                        out_string, save_file = handler.replace(value.get("content"),
                                                                assist_device_ident=assist_device_ident)
                    except EblockCannotFindFile as ex:  # 解释失败,不记录结果
                        logger.error(f"unit replace fail {ex}")
                        return
                    if save_file:
                        save_list.append(save_file)
                    if out_string:
                        cmd_dict[key] = out_string
                logger.debug("----replace other macro finished in eblock----")
                cmd_dict["functionName"] = self.functionName
                sending_data = {"execCmdDict": cmd_dict}
                target = "ImageHandler" if self.execModName == "IMGTOOL" else "ComplexHandler"
            sending_data["work_path"] = handler.work_path
            sending_data["device_label"] = self.device_label
            if self.ocrChoice:
                sending_data["ocr_choice"] = self.ocrChoice
            if assist_device_ident:
                sending_data["assist_device_serial_number"] = assist_device_ident
            logger.info(f"unit:{sending_data}")
            self.detail = UnitFactory().create(target, sending_data)

            logger.debug(f"unit finished result:{self.detail}")
            self.copy_save_file(save_list, handler)

            # def _replace(item_iter,saving_container):
            #     save_list = []
            #     for item in item_iter:
            #         try:
            #             value = saving_container.get(item) if isinstance(saving_container,dict) else item
            #             replaced_cmd, save_file = handler.replace(value, assist_device_ident=assist_device_ident)
            #         except EblockCannotFindFile as ex:  # 解释失败,不记录结果
            #             logger.error(f"unit replace fail {ex}")
            #             return
            #         if save_file:
            #             save_list.append(save_file)
            #         if replaced_cmd and isinstance(saving_container, dict):
            #             if isinstance(saving_container, dict):
            #                 saving_container[item] = replaced_cmd
            #             else:
            #                 saving_container.append(replaced_cmd)
            #     return save_list,saving_container

        return _inner_func()

    def copy_save_file(self, save_list, handler: MacroHandler):
        """
        针对需要推送给reef 的文件 将其复制到rds path

        针对ocr模块 临时提供解决方案
        """
        for file in os.listdir(handler.work_path):
            # 普通unit产生的图片可能会被下一个unit使用，因此只能copy
            if file in save_list:
                shutil.copyfile(os.path.join(handler.work_path, file),
                                os.path.join(handler.rds_path, f"({handler.block_index}_{self.unit_list_index}){file}"))
            elif file.startswith("ocr-"):
                # 复合型unit产生的图片只有自己会使用，因此move即可
                shutil.move(os.path.join(handler.work_path, file),
                            os.path.join(handler.rds_path, f"({handler.block_index}_{self.unit_list_index}){file}"))
