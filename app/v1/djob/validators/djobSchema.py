from marshmallow import fields, validate

from app.libs.extension.schema import BaseSchema
from app.v1.djob.config.setting import TBOARD, DJOB, FLOW_EXECUTE_MODE


class UIJsonSchema(BaseSchema):
    id = fields.Integer(required=True)
    order = fields.Integer(required=True)
    name = fields.Str(required=True)


class DJobSchema(BaseSchema):
    """
     {
        "device_label": device_label,
        "job_label": job_label,
        "source": "Tbod",
        "tboard_id": tboard_id
    }
    """

    device_label = fields.Str(required=True)
    job_label = fields.Str(required=True)
    # 指定从哪里下发
    source = fields.Str(required=True, validate=validate.OneOf([TBOARD, DJOB]))
    tboard_id = fields.Integer(required=True)
    flow_execute_mode = fields.Str(required=True, validate=validate.OneOf(FLOW_EXECUTE_MODE))
    job_flows = fields.Nested(UIJsonSchema, many=True, required=True)
    tboard_path = fields.Str(required=True)


if __name__ == '__main__':
    a = {'device_label': 'chiron---msm8998---5d7032d2', 'job_label': 'job-302a99e8-2f3b-30ec-de07-36328ce3a94d',
     'flow_execute_mode': 'SingleSplit', 'job_flows': [{'id': 313, 'order': 0}], 'source': 'tboard',
     'tboard_id': '658638', 'tboard_path': '/Users/darr_en1/tianjinproject/Tboard/658638/'}
    validate_data = DJobSchema().load_or_parameter_exception(a)
    print(validate_data)