from app.libs.extension.field import DictField
from app.libs.extension.model import BaseModel


class BouncedWords(BaseModel):
    words = DictField()
    load = ("words",)

    def __init__(self, *args, **kwargs):
        super(BouncedWords, self).__init__(*args, **kwargs)
