from flask import request
from flask.views import MethodView

from app.v1.eblock.model.eblock import Eblock
from app.v1.eblock.validators.tboardSchema import EblockSchema

eblock_schema = EblockSchema()


class EblockView(MethodView):

    def post(self):
        data = request.get_json()
        eblock = insert_eblock(data)
        return eblock.json(), 200

    def delete(self, id):
        stop_eblock(id)
        return "Succeed to stop eblock", 204


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
