# https://marshmallow.readthedocs.io/en/stable/quickstart.html#declaring-schemas
from marshmallow import EXCLUDE, ValidationError

from app.execption.outer.error_code.total import ParameterException
from extensions import ma


class BaseSchema(ma.Schema):
    class Meta:
        datetimeformat = '%Y_%m_%d_%H_%M_%S'
        unknown = EXCLUDE
        ordered = True

    def load_or_parameter_exception(self, data, *, many=None, partial=None, unknown=None):
        # https://www.zhihu.com/question/287097169/answer/453176871
        try:
            return super().load(data, many=many, partial=partial, unknown=unknown)
        except ValidationError as err:
            raise ParameterException(description=err.messages, code=400)
