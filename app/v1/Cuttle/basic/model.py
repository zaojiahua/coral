from astra import models

from app.libs.extension.model import BaseModel
from app.libs.log import setup_logger


class AdbDevice(BaseModel):
    is_connected = models.BooleanField()
    is_busy = models.BooleanField()
    disconnect_times = models.IntegerField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(f'adb-server{self.pk}', f'adb-server-{self.pk}.log')
        self.is_busy = False


class HandDevice(BaseModel):
    is_busy = models.BooleanField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = setup_logger(f'hand-server{self.pk}', f'hand-server-{self.pk}.log')
        self.is_busy = False

