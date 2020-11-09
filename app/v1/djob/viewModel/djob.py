import datetime

from app.v1.djob.model.device import DjobDevice
from app.v1.djob.model.job import Job


class DJob:
    def __init__(self, device: DjobDevice, job: Job, start_time: datetime.datetime):
        self.device = device
        self.job = job
        self.start = start_time
        self.stop_flag = False
