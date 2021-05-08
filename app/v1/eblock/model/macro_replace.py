import os
import re
import time

from app.config.ip import REEF_IP
from app.config.url import simcard_url, account_url
from app.execption.outer.error_code.eblock import EblockCannotFindFile, MaroUnrecognition, \
    EblockResourceMacroWrongFormat, DeviceNeedResource
from app.execption.outer.error_code.total import RequestException
from app.libs.http_client import request

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
adb_ip_prefix = "<3adbcIP>"
Rotate_horizontal = "<RotateHorizontal>"
Rotate_vertical = "<RotateVertical>"
Rotate_switch = "<RotateSwitch>"
Rotate_switchHold = "<RotateSwitchHold>"
RotateNormal = "<RotateNormal>"
RotateInit = "<RotateInit>"
RotateUp = '<RotateUp>'
Resource = "<Res_"
Phone = "<Pho_"

job_editor_logo = "Tmach"

macro_list = []
macro_dict = {
    adb_ip_prefix: REEF_IP,
    Rotate_horizontal: "G01 X0Y33Z90F7000 \r\n",
    Rotate_vertical: "G01 X0Y33Z0F7000 \r\n",
    Rotate_switch: "G01 X34Y33Z0F1500 \r\n<move>",
    Rotate_switchHold: "G01 X34Y33Z0F1500 \r\n<move><rotateSleep>",
    RotateNormal: "G01 X0Y33Z0F5000 \r\n",
    RotateInit: "G01 X0Y00Z0F5000 \r\n",
    RotateUp: "G01 X0Y123Z0F3000 \r\n"
}


class MacroHandler(object):
    _adb_cmd_prefix = "adb "

    def __init__(self, work_path, rds_path, ip_address, block_index, temp_port_list=None, **kwargs):
        self.block_index = block_index
        self.work_path = work_path
        self.rds_path = rds_path
        self.device_temp_port_list = temp_port_list
        self.ip_address = ip_address

    def replace(self, cmd, **kwargs):
        assist_device_ident = kwargs.pop("assist_device_ident", None)
        save_file = ""
        if job_editor_logo in cmd:
            for i in re.findall("Tmach(.*?) ", cmd):
                cmd = re.sub("Tmach.*? ", i, cmd, count=1)
        if content_singal in cmd:
            res = re.search("<Macro_(.*?)>", cmd)
            # file_name = res.group(1) + ".txt" if res.group(1).split(".") == 1 else res.group(1)
            file_name = res.group(1)
            position_path = os.path.join(self.work_path, file_name)
            if not os.path.exists(position_path):
                raise EblockCannotFindFile
            with open(position_path, "r") as f:
                position = f.read()
                cmd = re.sub("<Macro_.*?>", position.strip(), cmd)
        if Resource in cmd:
            # <Re_appname_type>
            res = re.search("<Res_(.*?)>", cmd)
            resource = res.group(1)
            if resource.split("_") < 2:
                raise EblockResourceMacroWrongFormat
            app_name = resource.split("_")[0]
            type = resource.split("_")[1]
            device_id = kwargs.get("device_id", None)
            try:
                response = request(url=account_url, params={"app_name": app_name,
                                                            "device__device_label": device_id,
                                                            "fields": "name,username,password"}, filter_unique_key=True)
            except RequestException:
                raise DeviceNeedResource
            content = response.get(type)
            re.sub("<Macro_.*?>", content, cmd)
        if Phone in cmd:
            res = re.search("<Pho_(.*?)>", cmd)
            sim_number = res.group(1)
            device_id = kwargs.get("device_id", None)
            try:
                response = request(url=simcard_url, params={"device__device_label": device_id, "order": sim_number,
                                                            "fields": "phone_number"},
                                   filter_unique_key=True)
            except RequestException:
                raise DeviceNeedResource
            phone_number = response.get("phone_number")
            re.sub("<Macro_.*?>", phone_number, cmd)
        if copy_singal in cmd:
            res = re.search("<blkOutPath>(.*?)<copy2rdsDatPath>", cmd)
            cmd = cmd.replace("<copy2rdsDatPath>", "")
            try:
                save_file = res.group(1) + ".log" if res.group(1).split(".") == 1 else res.group(1)
            except AttributeError:
                print("wait for re:", cmd)
                raise MaroUnrecognition
        for work_path_macro in [block_output_path, adb_data_path, block_input_path]:
            if work_path_macro in cmd:
                cmd = cmd.replace(work_path_macro, self.work_path)
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
                cmd = cmd.replace(key, value)
                break
        if adb_ip_prefix in cmd:
            cmd = cmd.replace(adb_ip_prefix, REEF_IP)
        if adb_tool_prefix in cmd:
            script = f" -s {assist_device_ident}" if assist_device_ident else f"-s {self.ip_address}"
            cmd = cmd.replace(adb_tool_prefix, script)
            cmd = self._adb_cmd_prefix + " " + cmd
        return cmd, save_file
