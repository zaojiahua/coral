import json
import logging
import os

from flask import request, jsonify
from flask.views import MethodView

from app.config.setting import TOTAL_LOG_NAME
from app.libs.ospathutil import makedirs_new_folder, deal_dir_file, asure_path_exist
from app.v1.djob.viewModel.device import DeviceViewModel
from app.v1.djob.viewModel.job import macro_repalce
from app.v1.eblock.model.eblock import Eblock
from app.v1.eblock.model.macro_replace import MacroHandler
from app.v1.eblock.model.unit import Unit
from app.v1.eblock.validators.tboardSchema import EblockSchema, UnitSchema
from app.v1.eblock.model.bounced_words import BouncedWords
from app.v1.Cuttle.basic.common_utli import reset_arm
from app.v1.Cuttle.basic.setting import CAMERA_CONFIG_FILE, set_global_value

eblock_schema = EblockSchema()

logger = logging.getLogger(TOTAL_LOG_NAME)


class EblockView(MethodView):

    def post(self):
        data = request.get_json()
        eblock = insert_eblock(data)
        return eblock.json(), 200

    def delete(self, id):
        stop_eblock(id)
        return "Succeed to stop eblock", 204


class UnitView(MethodView):

    def post(self):
        from app.v1.device_common.device_model import Device
        data = json.loads(request.form["data"])

        device_vm = DeviceViewModel(device_label=data["device_label"],
                                    flow_id=0)

        data = macro_repalce(data, device_vm.djob_work_path)

        validate_data = UnitSchema().load_or_parameter_exception(data)

        makedirs_new_folder(device_vm.rds_data_path)
        makedirs_new_folder(device_vm.djob_work_path)
        asure_path_exist(device_vm.share_path)
        device_vm._get_device_msg()

        handler = MacroHandler(
            work_path=device_vm.djob_work_path,
            rds_path=device_vm.rds_data_path,
            ip_address=Device(pk=validate_data["device_label"]).connect_number,
            block_index=0,
            share_path=device_vm.share_path)

        fs = request.files.getlist('file')

        for f in fs:
            f.save(os.path.join(device_vm.djob_work_path, f.filename))

        unit = Unit(unit_list_index=1, **validate_data)
        try:
            # 调试用例的时候，重试一次
            unit.process_unit(logger, handler, test_running=True, max_retry_time=1)
        finally:
            deal_dir_file(device_vm.base_path)

        return unit.detail, 200


class BouncedWordsView(MethodView):

    def post(self):
        request_data = request.get_json()
        print('收到的干扰词更新是：', request_data)

        # add new bounced words
        bounced_words = BouncedWords.first()
        new_words = bounced_words.words
        for w_k, w_v in request_data.items():
            new_words[w_k] = w_v
        bounced_words.words = new_words

        return bounced_words.words, 200

    def delete(self):
        # 删除的时候遍历id
        request_data = request.get_json()
        print('delete 收到的干扰词更新是：', request_data)

        # delete bounced words
        bounced_words = BouncedWords.first()
        current_bounced_words = bounced_words.words
        for delete_key in request_data:
            if str(delete_key) in current_bounced_words:
                del current_bounced_words[str(delete_key)]
        bounced_words.words = current_bounced_words

        return bounced_words.words, 200


# --------------------------For Internal calls-------------------------------
def insert_eblock(data):
    # 4种情况：
    # 1.第一次进入                       生成对象&开始&加入电量测试
    # 2.进入过&正在执行                  拒绝
    # 3.进入过&执行完毕&超过300s         获取对象&开始&加入电量测试&重置时间
    # 4.进入过&执行完毕&不足300s         获取对象&开始
    with eblock_schema.load_or_parameter_exception(data) as eblock:
        result = eblock.start()
    eblock.logger.info(f"eblock execute result:{result}")
    return eblock


def stop_eblock(id):
    eblock_instance = Eblock(pk=id)
    eblock_instance.stop()
    return 0


# 复位机械臂
class ArmResetView(MethodView):

    def post(self):
        request_data = request.get_json()
        device_label = request_data.get('device_label') if request_data else ''
        # 传入端口号 复位哪个机械臂
        arm_com = request_data.get('arm_com') if request_data else ''

        if not device_label:
            return jsonify(dict(code=1, message='need device label!'))

        result = reset_arm(device_label, arm_com)
        return jsonify(dict(code=result))


# 相机参数配置相关
class CameraConfigView(MethodView):

    def get(self):
        request_data = request.get_json()
        # 为以后四摄做准备
        camera_index = request_data.get('camera_index') if request_data else 0

        return jsonify(dict(code=0, data=self.get_camera_config(camera_index)))

    def post(self):
        request_data = request.get_json()

        if request_data is None:
            return jsonify(dict(code=1, message='缺少必要的参数'))

        # 为四摄做准备
        camera_index = request_data.get('camera_index') if request_data else 0

        try:
            camera_config = {}
            with open(CAMERA_CONFIG_FILE, 'rt', encoding='utf-8') as f:
                for line in f.readlines():
                    if '=' not in line:
                        continue
                    key, value = [k.strip() for k in line.strip('\n').split('=')]
                    if key in request_data:
                        camera_config[key] = request_data.get(key)
                    else:
                        camera_config[key] = value

            print(camera_config)
            # 写入到文件中  # 写入到内存中
            with open(CAMERA_CONFIG_FILE, 'wt', encoding='utf-8') as f:
                for key, value in camera_config.items():
                    f.writelines(f'{key} = {value}\n')
                    set_global_value(key, value)
        except Exception as e:
            print(e)

        return jsonify(dict(code=0, data=self.get_camera_config(camera_index)))

    @staticmethod
    def get_camera_config(camera_index=0):
        camera_config = {}
        try:
            with open(CAMERA_CONFIG_FILE, 'rt', encoding='utf-8') as f:
                for line in f.readlines():
                    if '=' not in line:
                        continue
                    key, value = line.strip('\n').split('=')
                    camera_config[key.strip()] = value.strip()
        except Exception as e:
            print(e)

        return camera_config
