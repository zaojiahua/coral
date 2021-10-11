import json
import logging
import os

from flask import request
from flask.views import MethodView

from app.config.setting import TOTAL_LOG_NAME
from app.libs.ospathutil import makedirs_new_folder, deal_dir_file
from app.v1.djob.viewModel.device import DeviceViewModel
from app.v1.djob.viewModel.job import macro_repalce
from app.v1.eblock.model.eblock import Eblock
from app.v1.eblock.model.macro_replace import MacroHandler
from app.v1.eblock.model.unit import Unit
from app.v1.eblock.validators.tboardSchema import EblockSchema, UnitSchema
from v1.eblock.model.bounced_words import BouncedWords

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
        device_vm._get_device_msg()

        handler = MacroHandler(
            work_path=device_vm.djob_work_path,
            rds_path=device_vm.rds_data_path,
            ip_address=Device(pk=validate_data["device_label"]).connect_number,
            block_index=0)

        fs = request.files.getlist('file')

        for f in fs:
            f.save(os.path.join(device_vm.djob_work_path, f.filename))

        unit = Unit(unit_list_index=1, **validate_data)
        try:
            unit.process_unit(logger, handler, test_running=True)
        finally:
            deal_dir_file(device_vm.base_path)

        return unit.detail, 200


class BouncedWordsView(MethodView):

    def post(self):
        request_data = request.get_json()

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
