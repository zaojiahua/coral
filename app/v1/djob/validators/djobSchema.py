from marshmallow import fields, validate

from app.libs.extension.schema import BaseSchema
from app.v1.djob.config.setting import TBOARD, DJOB


class UIJsonSchema(BaseSchema):
    id = fields.Integer(required=True)
    order = fields.Integer(required=True)


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
    flow_execute_mode = fields.Str(required=True)
    job_flows = fields.Nested(UIJsonSchema, many=True, required=True)
    tboard_path = fields.Str(required=True)
