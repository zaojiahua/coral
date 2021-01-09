import time

from marshmallow import fields, post_load, validate

from app.libs.extension.schema import BaseSchema
from app.v1.tboard.validators.role import Role
from app.v1.tboard.viewModel.tborad import TBoardViewModel


def get_tboard_default_name():
    return 'TBoard-{:.0f}'.format(time.time())


class UIJsonFileSchema(BaseSchema):
    id = fields.Integer(required=True)
    order = fields.Integer(required=True)


class JobSchema(BaseSchema):
    flow_execute_mode = fields.Str(required=True)
    job_flows = fields.Nested(UIJsonFileSchema, many=True, required=True)
    job_label = fields.Str(required=True)
    updated_time = fields.Str(required=True)
    url = fields.Str(required=True)
    inner_job = fields.Nested("self", many=True, only=["job_label", "updated_time", "url"])


class TboardSchema(BaseSchema):
    """
    missing指定字段的默认反序列化值。UserSchema().load({})
    default指定默认序列化值。UserSchema().dump({})
    """
    tboard_id = fields.Integer(required=True)
    board_name = fields.Str(missing=get_tboard_default_name)
    device_label_list = fields.List(fields.Str(required=True), required=True)
    jobs = fields.Nested(JobSchema, many=True, required=True)
    repeat_time = fields.Integer(missing=1)
    owner_label = fields.Str(required=True)
    create_level = fields.Str(missing="USER", validate=validate.OneOf(Role.__members__))

    # # extends
    # class Meta(BaseSchema.Meta):
    #     # additional 添加指定字段
    #     additional = ('owner_id',)
    #     # 要保持字段排序，请将ordered选项设置为True。
    #     # 这将指示棉花糖将数据序列化为collections.OrderedDict
    #     ordered = True

    @post_load
    def make_user(self, data, **kwargs):
        if not data.get("board_name"):
            data["board_name"] = get_tboard_default_name()

        # data = self.computer_repeat_time(data)

        return TBoardViewModel(**data)

    # @staticmethod
    # def computer_repeat_time(data):
    #     """
    #     优化repeat_time，缩短job_label_list长度
    #     :return:
    #     """
    #     job_label_dict = defaultdict(int)
    #     for job_label in data["job_label_list"]:
    #         job_label_dict[job_label] += 1
    #
    #     gcd_val = list_gcd(job_label_dict.values())
    #
    #     repeat_time = data["repeat_time"] * gcd_val
    #
    #     job_label_list = []
    #     for job_label, num in job_label_dict.items():
    #         job_label_list += [job_label] * (num // gcd_val)
    #
    #     data["repeat_time"] = repeat_time
    #     data["job_label_list"] = job_label_list
    #     return data


if __name__ == '__main__':
    aaa = {
        "tboard_id": 78370,
        "create_level": "USER",
        "owner_label": "3",
        "jobs": [
            {
                "job_label": "job-459320f1-71e8-10b8-2c21-08dd8e10de48",
                "updated_time": "2020-08-21 08:59:43",
                "url": "/media/job_res_file_export/job-459320f1-71e8-10b8-2c21-08dd8e10de48.zip",
                "inner_job": [
                    {
                        "job_label": "job-3578512a-f9a4-52aa-161b-958e645c8e06",
                        "updated_time": "2020-08-21 08:59:43",
                        "url": "/media/job_res_file_export/job-3578512a-f9a4-52aa-161b-958e645c8e06.zip"
                    }
                ]

            }
        ],
        "board_name": "TBoard1598254971",
        "repeat_time": 1,
        "device_label_list": ["polaris---sdm845---b6922eb4"]
    }

    TboardSchema().load(aaa)
