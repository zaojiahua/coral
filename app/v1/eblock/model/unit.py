import copy
import os
import shutil
import subprocess
import time
from functools import lru_cache

import cv2
from astra import models
from func_timeout import func_set_timeout

from app.config.ip import ADB_TYPE
from app.config.setting import Bugreport_file_name, PICTURE_COMPRESS_RATIO
from app.config.url import device_url
from app.execption.outer.error import APIException
from app.execption.outer.error_code.djob import AssistDeviceOrderError, AssistDeviceNotFind
from app.execption.outer.error_code.eblock import EblockCannotFindFile
from app.libs.extension.field import DictField, OwnerList
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.eblock.config.leadin import PROCESSER_LIST
from app.v1.eblock.config.setting import DEFAULT_TIMEOUT
from app.v1.eblock.model.macro_replace import MacroHandler
from app.execption.outer.error_code.imgtool import DetectNoResponse
from app.libs.ospathutil import get_picture_create_time


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
    tGuard = models.IntegerField()
    unit_list_index = models.IntegerField()
    pictures = OwnerList(to=str)
    timestamps = OwnerList(to=str)
    unit_work_path = models.CharField()
    optionalInputImage = models.IntegerField()

    load = ("detail", "key", "execModName", "jobUnitName", "finalResult", 'pictures', 'timestamps', 'assistDevice')

    def __init__(self, pk=None, **kwargs):
        super().__init__(pk, **kwargs)
        self.unit_work_path = str(time.time())

    def process_unit(self, logger, handler: MacroHandler, **kwargs):
        assist_device_ident = get_assist_device_ident(self.device_label,
                                                      self.assistDevice) if self.assistDevice else None

        self.unit_work_path = os.path.join(handler.work_path, self.unit_work_path) + os.sep
        if not os.path.exists(self.unit_work_path):
            os.makedirs(self.unit_work_path)

        def _inner_func():
            # 默认保存bugreport.zip 根据2021/7/2客户需求，储存并下载zip文件
            save_list = [Bugreport_file_name]
            cmd_dict: dict = self.execCmdDict

            if 'ADBC' == self.execModName:
                # only want content， get ride of meaning&type
                cmd_list = [i.get("content") for i in cmd_dict.get("execCmdList")]
                repalced_cmd_list = []
                for cmd in cmd_list:
                    try:
                        replaced_cmd, save_file = handler.replace(cmd,
                                                                  unit_work_path=self.unit_work_path,
                                                                  assist_device_ident=assist_device_ident,
                                                                  device_label=self.device_label)
                    except EblockCannotFindFile as ex:  # 解释失败,不记录结果
                        logger.error(f"unit replace fail {ex}")
                        self.detail = {"result": ex.error_code}
                        return
                    if save_file:
                        save_list.append(save_file)
                    if replaced_cmd:
                        repalced_cmd_list.append(replaced_cmd)
                logger.debug("----replace adb macro finished in eblock--(adbc)--")
                cmd_dict["execCmdList"] = repalced_cmd_list

                sending_data = {"device_label": self.device_label, "ip_address": handler.ip_address, **cmd_dict}

                if assist_device_ident is None:
                    from app.v1.device_common.device_model import Device
                    if Device(pk=self.device_label).has_arm and cmd_dict.get("have_second_choice", 0) == 1:
                        target = PROCESSER_LIST[1]
                    elif Device(pk=self.device_label).has_camera and cmd_dict.get("have_second_choice", 0) == 2:
                        target = PROCESSER_LIST[2]
                    elif Device(pk=self.device_label).has_rotate_arm and cmd_dict.get("have_second_choice", 0) == 3:
                        target = PROCESSER_LIST[1]
                    elif Device(pk=self.device_label).has_arm and Device(
                            pk=self.device_label).has_camera and cmd_dict.get("have_second_choice", 0) == 4:
                        target = PROCESSER_LIST[1]
                    else:
                        target = PROCESSER_LIST[0]
                else:
                    target = PROCESSER_LIST[0]

            else:
                for key, value in cmd_dict.items():
                    try:
                        out_string, save_file = handler.replace(value.get("content"),
                                                                unit_work_path=self.unit_work_path,
                                                                cmd_key=key,
                                                                assist_device_ident=assist_device_ident,
                                                                device_label=self.device_label)
                    except EblockCannotFindFile as ex:  # 解释失败,不记录结果
                        logger.error(f"unit replace fail {ex}")
                        self.detail = {"result": ex.error_code}
                        return
                    if save_file:
                        save_list.append(save_file)
                    if out_string:
                        cmd_dict[key] = out_string
                logger.debug("----replace other macro finished in eblock----")
                cmd_dict["functionName"] = self.functionName
                sending_data = {"execCmdDict": cmd_dict}
                target = "ImageHandler" if self.execModName == "IMGTOOL" else "ComplexHandler"
            if kwargs.pop("test_running", False):
                sending_data["test_running"] = True
            sending_data["work_path"] = self.unit_work_path
            sending_data["device_label"] = self.device_label
            sending_data['timeout'] = self.timeout
            if self.ocrChoice:
                sending_data["ocr_choice"] = self.ocrChoice
            if self.tGuard:
                sending_data['t_guard'] = self.tGuard
            if assist_device_ident:
                sending_data["assist_device_serial_number"] = assist_device_ident
            if self.optionalInputImage:
                sending_data['optional_input_image'] = self.optionalInputImage
            logger.info(f"unit:{sending_data}")
            try:
                for i in range(3):
                    # # 给Tguard 留下发现重试执行当前unit的机会
                    self.detail = UnitFactory().create(target, sending_data)
                    if self.detail.get("result") == 666:
                        continue
                    else:
                        break
                else:
                    # 三次Tguard后unit结果设置为1
                    result = copy.deepcopy(self.detail)
                    result.update({"result": 1})
                    self.detail = result
            except DetectNoResponse as e:
                self.detail = {"result": e.error_code}
                raise e
            except Exception as e:
                logger.debug(f'unit 不正常结束 {e}')
                if isinstance(e, APIException):
                    detail = {"result": e.error_code}
                    if hasattr(e, 'extra_result'):
                        for k, v in e.extra_result.items():
                            detail[k] = v
                    self.detail = detail
                else:
                    raise e
            finally:
                self.copy_save_file(save_list, handler)

        return _inner_func()

    def save_picture_info(self, target_name, target_path):
        self.pictures.lpush(target_name)
        self.timestamps.lpush(get_picture_create_time(target_path))

    def copy_save_file(self, save_list, handler: MacroHandler):
        """
        针对需要推送给reef 的文件 将其复制到rds path

        针对ocr模块 临时提供解决方案
        """
        self.remove_duplicate_pic(self.unit_work_path)
        for file in os.listdir(self.unit_work_path):
            if file == Bugreport_file_name and self.assistDevice:
                target_name = f"({handler.block_index}_{self.unit_list_index}){file.split('.')[0]}-{self.assistDevice}.{file.split('.')[1]}"
            else:
                target_name = f"({handler.block_index}_{self.unit_list_index}){file}"
            target_path = os.path.join(handler.rds_path, target_name)
            # 一个公共读的目录 一个block内的其他unit需要用到之前unit的图片 或者跨block图片的使用 所以需要复制到一个公共的读目录以供其他unit使用
            target_read_path = os.path.join(handler.work_path, file)
            # 普通unit产生的图片可能会被下一个unit使用，因此只能copy
            if file in save_list:
                # 循环执行用例的时候，文件名是相同的，需要进行覆盖
                shutil.copyfile(os.path.join(self.unit_work_path, file), target_read_path)
                if not os.path.exists(target_path):
                    shutil.copyfile(os.path.join(self.unit_work_path, file), target_path)
                    if Bugreport_file_name not in target_name:
                        self.save_picture_info(target_name, target_path)
            elif file.startswith("ocr-") or file.startswith("crop-") or file.endswith("-crop.png") or file.endswith(
                    "-Tguard.png"):
                # 在windows平台的时候，如果图片是空，执行这个指令的时候会报错
                try:
                    # 复合型unit产生的图片只有自己会使用，因此move即可
                    shutil.move(os.path.join(self.unit_work_path, file), target_path)
                except Exception:
                    pass
                self.save_picture_info(target_name, target_path)
            else:
                # 其他情况下复制到公共读的目录 比如txt文件等 其他unit需要用到
                shutil.copyfile(os.path.join(self.unit_work_path, file), target_read_path)

            # 针对结果为0的unit，进行rds图片的压缩，为了减小体积
            if self.detail.get("result") == 0:
                if os.path.exists(target_path):
                    # 针对png图片进行压缩
                    if target_path.endswith('png'):
                        # 先缩放
                        origin_pic = cv2.imread(target_path, cv2.IMREAD_COLOR)
                        if origin_pic is not None:
                            origin_size = origin_pic.shape
                            new_size = (
                                int(origin_size[1] * PICTURE_COMPRESS_RATIO),
                                int(origin_size[0] * PICTURE_COMPRESS_RATIO))
                            compress_pic = cv2.resize(origin_pic, new_size)
                            cv2.imwrite(target_path, compress_pic)
                            # 后压缩
                            self.pngquant_compress(target_path)

    @staticmethod
    def pngquant_compress(fp):
        command = f'pngquant {fp} -f --quality 100-100'
        subprocess.run(command, shell=True)

    @staticmethod
    def remove_duplicate_pic(path):
        for file in os.listdir(path):
            file_name = ".".join(file.split(".")[:-1])
            # 手机推送出来的图片可能是jpg和png两种格式
            similar_file = os.path.join(path, file_name[:-5] + ".jpg")
            similar_file_2 = os.path.join(path, file_name[:-5] + ".png")
            if file_name.endswith("crop") and (os.path.exists(similar_file) or os.path.exists(similar_file_2)):
                src_crop = cv2.imread(os.path.join(path, file))
                src = cv2.imread(os.path.join(path, file_name[:-5] + ".jpg"))
                src_2 = cv2.imread(os.path.join(path, file_name[:-5] + ".png"))
                src = src if src is not None else src_2
                # 名称前缀相同，且图片尺寸相同则认为是没经过裁剪
                if src_crop is not None and src is not None and src_crop.shape == src.shape:
                    try:
                        os.remove(os.path.join(path, file))
                        print("delete one pic。。。")
                    except FileNotFoundError:
                        print("unable to find similar file to delete")
                    except Exception as e:
                        print('移除相似文件遇到其他异常', e)
