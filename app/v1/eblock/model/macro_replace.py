import os
import re
import time

from app.config.ip import REEF_IP
from app.config.url import simcard_url, account_url, device_assis_url
from app.execption.outer.error_code.eblock import \
    EblockResourceMacroWrongFormat, DeviceNeedResource, DeviceNeedRelativeAssisDevice, AssisDeviceNotHaveMainDevie
from app.execption.outer.error_code.total import RequestException
from app.libs.http_client import request
from app.execption.outer.error_code.eblock import EblockCannotFindFile, MaroUnrecognition
from app.v1.Cuttle.basic.setting import arm_default, hand_origin_cmd_prefix, arm_default_y, HAND_MAX_X, HAND_MAX_Y, \
    HAND_MAX_Z, get_global_value
from app.config.setting import find_command

adb_data_path = "<adbOutPath>"
block_index = "<blockIndex>"
block_input_path = "<blkInpPath>"
block_output_path = "<blkOutPath>"
rds_data_path = "<rdsDatPath>"
copy_singal = "<copy2rdsDatPath>"
device_temp_port_list = "<deviceTemperPort>"
long_time_sleep_tag = "<longTimeSleepTag_"
content_singal = "<Macro_"
adb_tool_prefix = "<3adbcTool>"
fastboot_tool_prefix = "<fastbootTool>"
adb_ip_prefix = "<3adbcIP>"
Rotate_horizontal = "<RotateHorizontal>"
Rotate_vertical = "<RotateVertical>"
Rotate_switch = "<RotateSwitch>"
Rotate_switchHold = "<RotateSwitchHold>"
RotateNormal = "<RotateNormal>"
RotateInit = "<RotateInit>"
RotateUp = '<RotateUp>'
# 旋转机械臂原始移动
RotateOrigin = '<RotateOrigin>'
rotate_origin_x_range = [-90, 90]
rotate_origin_y_range = [-33, 90]
rotate_origin_z_range = [-180, 180]
# 用户写的单位是 毫米/秒 实际需要的单位是 毫米/秒
rotate_origin_f_range = [600 / 60, 9000 / 60]
# 三轴机械臂原始移动
HandOrigin = '<HandOrigin>'
hand_origin_f_range = [600 / 60, 15000 / 60]
Resource = "<Acc_"
Phone = "<Sim_"
pipe_command = "<FindCommand>"

job_editor_logo = "Tmach"

macro_list = []
macro_dict = {
    adb_ip_prefix: REEF_IP,
    Rotate_horizontal: "G01 X0Y33Z90F7000 \r\n",
    Rotate_vertical: "G01 X0Y33Z0F7000 \r\n",
    Rotate_switch: "G01 X34Y33Z0F1500 \r\n<move>",
    Rotate_switchHold: "G01 X34Y33Z0F1500 \r\n<move><rotateSleep>",
    RotateNormal: arm_default,
    RotateInit: "G01 X0Y00Z0F5000 \r\n",
    RotateUp: "G01 X0Y123Z0F7000 \r\n",
    RotateOrigin: "G01",
    HandOrigin: f'{hand_origin_cmd_prefix} G01'
}


class MacroHandler(object):
    _adb_cmd_prefix = "adb "
    _fastboot_cmd_prefix = 'fastboot'

    def __init__(self, work_path, rds_path, ip_address, block_index, temp_port_list=None, **kwargs):
        self.block_index = block_index
        self.work_path = work_path
        self.rds_path = rds_path
        self.device_temp_port_list = temp_port_list
        self.ip_address = ip_address

    def replace(self, cmd, unit_work_path, cmd_key=None, **kwargs):
        assist_device_ident = kwargs.pop("assist_device_ident", None)
        device_id = kwargs.get("device_label", None)
        save_file = ""
        if job_editor_logo in cmd:
            for i in re.findall("Tmach(.*?) ", cmd):
                cmd = re.sub("Tmach.*? ", i, cmd, count=1)
        if content_singal in cmd:
            res = re.search("<Macro_(.*?)>", cmd)
            # file_name = res.group(1) + ".txt" if res.group(1).split(".") == 1 else res.group(1)
            file_name = res.group(1)
            position_path = os.path.join(unit_work_path, file_name)
            if not os.path.exists(position_path):
                # 尝试从公共读目录读取
                position_path = os.path.join(self.work_path, file_name)
                if not os.path.exists(position_path):
                    raise EblockCannotFindFile
            with open(position_path, "r") as f:
                position = f.read()
                cmd = re.sub("<Macro_.*?>", position.strip(), cmd)
        if Resource in cmd:
            # <Re_appname_type>
            res = re.search("<Acc_(.*?)>", cmd)
            resource = res.group(1)
            if len(resource.split("_")) < 3:
                raise EblockResourceMacroWrongFormat
            app_name = resource.split("_")[0]
            type = resource.split("_")[1]
            phone_type = int(resource.split("_")[2])
            # 兼容用户输入简便，与数据库定义
            available_type = {"id": "name", "username": "username", "code": "password", 'phone': 'phone_number'}
            if type.lower() not in available_type.keys() or phone_type not in [0, 1, 2, 3]:
                raise EblockResourceMacroWrongFormat
            # 在僚机载体执行的unit，里面可能需要替换自己关联的主机的账号相关信息，也可能换自己关联的主机关联的其他僚机的账号相关信息
            if assist_device_ident:
                # 先找到了解的关联主机id
                try:
                    response = request(url=device_assis_url, params={"fields": "device.device_label",
                                                                     "status__in": "ReefList[idle{%,%}busy]",
                                                                     "serial_number": assist_device_ident},
                                       filter_unique_key=True)
                    host_device_id = response.get("device").get("device_label")
                except RequestException:
                    raise AssisDeviceNotHaveMainDevie
                # 主机宏的直接查询并正则替换
                if phone_type == 0:
                    d_params = {"device__device_label": host_device_id}
                else:
                    # 僚机的宏需要根据phone_type找到对应僚机的ser-num
                    relative_ass_device = self.find_relative_assis_device(host_device_id, phone_type)
                    d_params = {"subsidiary_device__serial_number": relative_ass_device}
                cmd = self.set_account_value(available_type, cmd, d_params, type, app_name)
            else:
                # 在主机载体执行，可以替换自己关联的资源信息，或自己关联的僚机关联的资源信息
                if phone_type == 0:
                    d_params = {"device__device_label": device_id}
                else:
                    relative_ass_device = self.find_relative_assis_device(device_id, phone_type)
                    d_params = {"subsidiary_device__serial_number": relative_ass_device}
                cmd = self.set_account_value(available_type, cmd, d_params, type, app_name)
        if Phone in cmd:
            res = re.search("<Sim_(.*?)>", cmd)
            sim_resource = res.group(1)
            if len(sim_resource.split("_")) < 2 :
                raise EblockResourceMacroWrongFormat
            sim_number = sim_resource.split("_")[0]
            phone_type = int(sim_resource.split("_")[1])
            if phone_type not in [0, 1, 2, 3]:
                raise EblockResourceMacroWrongFormat
            if phone_type == 0:
                d_params = {"device__device_label": device_id}
            else:
                relative_ass_device = self.find_relative_assis_device(device_id, phone_type)
                d_params = {"subsidiary_device__serial_number": relative_ass_device}
            cmd = self.set_sim_value(cmd, d_params, sim_number)
        if copy_singal in cmd:
            res = re.search("<blkOutPath>(.*?)<copy2rdsDatPath>", cmd)
            cmd = cmd.replace("<copy2rdsDatPath>", "")
            try:
                save_file = res.group(1) + ".log" if res.group(1).split(".") == 1 else res.group(1)
            except AttributeError:
                print("wait for re:", cmd)
                raise MaroUnrecognition
        # 当需要读取之前unit产生的图片时，从work_path目录中读取
        if cmd_key and cmd_key.startswith('inputImgFile'):
            for work_path_macro in [block_output_path]:
                if work_path_macro in cmd:
                    cmd = cmd.replace(work_path_macro, self.work_path)
        for work_path_macro in [block_output_path, adb_data_path, block_input_path]:
            if work_path_macro in cmd:
                cmd = cmd.replace(work_path_macro, unit_work_path)
        if rds_data_path in cmd:
            cmd = cmd.replace(rds_data_path, self.rds_path + os.path.sep)
        if not self.device_temp_port_list and device_temp_port_list in cmd:
            cmd = ""
        if device_temp_port_list in cmd and self.device_temp_port_list:
            cmd = self.device_temp_port_list
        if long_time_sleep_tag in cmd:
            sleep_time = int(cmd.lstrip(long_time_sleep_tag).strip(">"))
            time.sleep(sleep_time)
            cmd = "<4ccmd><sleep>0.1"
        for key, value in macro_dict.items():
            if key in cmd:
                if Rotate_switchHold == cmd:
                    res = re.search(f"{Rotate_switchHold}(.*?)$", cmd)
                    second = res.group(1)
                    value = value + str(second)
                if RotateOrigin == key or HandOrigin == key:
                    cmd = self.set_origin_rotate_param(cmd)
                    cmd = f'{cmd} \r\n'
                cmd = cmd.replace(key, value)
                break
        if adb_ip_prefix in cmd:
            cmd = cmd.replace(adb_ip_prefix, REEF_IP)
        if adb_tool_prefix in cmd:
            script = f" -s {assist_device_ident}" if assist_device_ident else f"-s {self.ip_address}"
            cmd = cmd.replace(adb_tool_prefix, script)
            cmd = self._adb_cmd_prefix + " " + cmd

        # 支持刷机指令
        if fastboot_tool_prefix in cmd:
            script = f" -s {assist_device_ident}" if assist_device_ident else f"-s {self.ip_address}"
            cmd = cmd.replace(fastboot_tool_prefix, script)
            cmd = self._fastboot_cmd_prefix + " " + cmd

        if pipe_command in cmd:
            cmd = cmd.replace(pipe_command, find_command)
        return cmd, save_file

    @staticmethod
    def get_validate_range(r_list, x):
        if x < r_list[0]:
            x = r_list[0]
        elif x > r_list[1]:
            x = r_list[1]
        return x

    @staticmethod
    def set_origin_rotate_param(cmd):
        pattern = r'X(.+)Y(.+)Z(.+)F(.+)'
        rotate_params = re.findall(pattern, cmd)
        if len(rotate_params) > 0:
            # 需要对范围进行限制 同时y方向减少33度
            if cmd.startswith(RotateOrigin):
                x = MacroHandler.get_validate_range(rotate_origin_x_range, int(rotate_params[0][0]))
                y = MacroHandler.get_validate_range(rotate_origin_y_range, int(rotate_params[0][1]))
                z = MacroHandler.get_validate_range(rotate_origin_z_range, int(rotate_params[0][2]))
                f = MacroHandler.get_validate_range(rotate_origin_f_range, int(rotate_params[0][3]))
                y = y + int(arm_default_y)
                spend_time = max(abs(x), abs(y), abs(z)) / f
                f = f * 60
                cmd = re.sub(pattern, f'X{x}Y{y}Z{z}F{f}', cmd)
                cmd += f'<rotateSleep>{spend_time}'
            elif cmd.startswith(HandOrigin):
                x = MacroHandler.get_validate_range([0, 100], int(rotate_params[0][0]))
                y = MacroHandler.get_validate_range([0, 100], int(rotate_params[0][1]))
                z = MacroHandler.get_validate_range([0, 100], int(rotate_params[0][2]))
                f = MacroHandler.get_validate_range(hand_origin_f_range, int(rotate_params[0][3]))
                x = x / 100 * HAND_MAX_X
                # 6 是由于硬件导致的安装误差
                y = -y / 100 * (HAND_MAX_Y - 6)
                z = z / 100 * (HAND_MAX_Z - get_global_value('Z_DOWN')) + get_global_value('Z_DOWN')
                spend_time = max(x, y, abs(z)) / f
                f = f * 60
                cmd = re.sub(pattern, f'X{x}Y{y}Z{z}F{f}', cmd)
                cmd += f'<rotateSleep>{spend_time}'
        return cmd

    def set_sim_value(self, cmd, d_params, sim_number):
        d_params.update({"order": sim_number, "fields": "phone_number"})
        try:
            response = request(url=simcard_url, params=d_params, filter_unique_key=True)
        except RequestException:
            raise DeviceNeedResource
        phone_number = response.get("phone_number")
        cmd = re.sub("<Sim_.*?>", phone_number, cmd)
        return cmd

    def find_relative_assis_device(self, host_device_id, phone_type):
        try:
            response = request(url=device_assis_url, params={"device__device_label": host_device_id,
                                                             "order": phone_type}, filter_unique_key=True)
            relative_ass_device = response.get("serial_number")
        except RequestException:
            raise DeviceNeedRelativeAssisDevice
        return relative_ass_device

    def set_account_value(self, available_type, cmd, d_params, type, app_name):
        d_params.update({"app_name": app_name, "fields": "name,username,password,phone_number"})
        try:
            response = request(url=account_url, params=d_params, filter_unique_key=True)
        except RequestException:
            raise DeviceNeedResource
        content = response.get(available_type.get(type.lower()))
        cmd = re.sub("<Acc_.*?>", content, cmd)
        return cmd
