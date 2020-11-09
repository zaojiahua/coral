class DJobWorker:
    def __init__(self, device_label):
        self.device_label = device_label
        self.djob_wait_list = []
