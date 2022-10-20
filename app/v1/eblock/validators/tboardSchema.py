from marshmallow import fields, post_load

from app.libs.extension.schema import BaseSchema


class UnitSchema(BaseSchema):
    key = fields.Integer(required=True)
    timeout = fields.Integer()
    execCmdDict = fields.Dict(required=True)
    execModName = fields.Str(required=True)
    jobUnitName = fields.Str()
    unitDescription = fields.Str()
    functionName = fields.Str()
    assistDevice = fields.Integer()
    finalResult = fields.Boolean()
    ocrChoice = fields.Integer()
    tGuard = fields.Integer()
    device_label = fields.Str()
    # 如果有这个字段，代表没有输入图片的时候，现截图一张
    optionalInputImage = fields.Integer()
    # 横屏还是竖屏 点击unit的时候需要
    portrait = fields.Integer()
    # 性能测试时候判断的字段
    start_method = fields.Integer()


class UnitListSchema(BaseSchema):
    key = fields.Integer(required=True)
    unit_list = fields.Nested(UnitSchema, many=True, required=True, data_key="unitList")


class EblockSchema(BaseSchema):
    pk = fields.Str(required=True)
    block_index = fields.Integer()
    device_id = fields.Str(required=True)
    stop_flag = fields.Boolean(missing=False)
    block_source = fields.Str(required=True)
    work_path = fields.Str(required=True)
    rds_path = fields.Str(required=True)
    temp_port_list = fields.List(fields.Str(), required=True)
    ip_address = fields.Str(required=True)
    unit_lists = fields.Nested(UnitListSchema, many=True, required=True, data_key="unitLists")
    block_name = fields.Str(data_key="blockName")
    job_parameter = fields.Raw(required=False)

    @post_load
    def make_user(self, validate_data, **kwargs):
        from app.v1.eblock.model.eblock import Eblock
        return Eblock(load=True, **validate_data)


if __name__ == '__main__':
    insert_eblock_data_sample = {'block_index': 1,
                                 'device_id': 'chiron---msm8998---5f5fb5be',
                                 'block_source': 'Djob',
                                 'work_path': 'E:\\Pacific\\chiron---msm8998---5f5fb5be\\djobwork\\',
                                 'rds_path': 'E:\\Pacific\\chiron---msm8998---5f5fb5be\\2020_03_31\\11_43_42\\',
                                 'temp_port_list': [],
                                 'ip_address': '10.80.3.47',
                                 'unitLists': [
                                     {
                                         "key": "-2",
                                         "unitList": [
                                             {
                                                 "execCmdDict": {
                                                     "bkupCmdList": [],
                                                     "execCmdList": [
                                                         {
                                                             "content": "<3adbcTool> shell input keyevent 4",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> shell input keyevent 4",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> shell input keyevent 4",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> shell input keyevent 3",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> shell input keyevent 3",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> shell input keyevent 3",
                                                             "type": "noChange"
                                                         }
                                                     ],
                                                     "exptResList": []
                                                 },
                                                 "execModName": "ADBC",
                                                 "jobUnitName": "\u56de\u5230\u684c\u9762",
                                                 "key": -7,
                                                 "unitDescription": "\u56de\u5230\u684c\u9762"
                                             }
                                         ]
                                     },
                                     {
                                         "key": "-5",
                                         "unitList": [
                                             {
                                                 "execCmdDict": {
                                                     "bkupCmdList": [],
                                                     "execCmdList": [
                                                         {
                                                             "content": "<3adbcTool> shell rm /sdcard/snap.png",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> shell screencap -p /sdcard/snap.png",
                                                             "type": "noChange"
                                                         },
                                                         {
                                                             "content": "<3adbcTool> pull /sdcard/snap.png <blkOutPath>Tmachsnap1-1.png<copy2rdsDatPath> ",
                                                             "meaning": "\u622a\u53d6\u5f53\u524d\u5c4f\u5e55\u622a\u56fe\uff0c\u9700\u8981\u8f93\u5165\u56fe\u7247\u6587\u4ef6\u540d",
                                                             "type": "outputPicture"
                                                         }
                                                     ],
                                                     "exptResList": []
                                                 },
                                                 "execModName": "ADBC",
                                                 "jobUnitName": "\u622a\u56fe\u4fdd\u5b58",
                                                 "key": -9,
                                                 "unitDescription": "snap shot to get a picture for next identification or save as raw data"
                                             }
                                         ]
                                     },
                                     {
                                         "key": "-6",
                                         "unitList": [
                                             {
                                                 "execCmdDict": {
                                                     "inputImgFile": {
                                                         "content": "<blkOutPath>Tmachsnap1-1.png ",
                                                         "meaning": "\u8f93\u5165\u4f20\u5165\u56fe\u7247\u7684\u6587\u4ef6\u540d\uff0c\u5176\u901a\u5e38\u6765\u81ea\u4e8e\u4e4b\u524d\u7684\u4e00\u4e2a\u622a\u56feUnit",
                                                         "type": "inputPicture"
                                                     },
                                                     "requiredWords": {
                                                         "content": "Tmach\u8bbe\u7f6e ",
                                                         "meaning": "\u8f93\u5165\u8981\u8bc6\u522b\u7684\u6587\u5b57",
                                                         "type": "uxInput"
                                                     },
                                                     "xyShift": {
                                                         "content": "Tmach0  Tmach-40 ",
                                                         "meaning": "\u8f93\u5165\u504f\u79fb\u91cfx\u548cy\uff08\u5411\u4e0a/\u5411\u5de6\u4e3a\u8d1f\u503c\uff09",
                                                         "type": "uxInput"
                                                     }
                                                 },
                                                 "execModName": "IMGTOOL",
                                                 "functionName": "get_ocr_position_and_point",
                                                 "jobUnitName": "\u6587\u5b57\u8bc6\u522b\u5e76\u70b9\u51fb",
                                                 "key": -8,
                                                 "unitDescription": "\u6839\u636e\u6587\u5b57\u67e5\u627e\u5e76\u70b9\u51fb\u5bf9\u5e94\u4f4d\u7f6e"
                                             }
                                         ]
                                     }
                                 ],
                                 'blockName': '进入设置'}
    print(EblockSchema().load(insert_eblock_data_sample))
