from libs.extension.field import DictField
from libs.extension.model import BaseModel


class BouncedWords(BaseModel):
    words = DictField()
    load = ("words")

    def __init__(self, pk=None, **kwargs):
        super().__init__(pk, **kwargs)
