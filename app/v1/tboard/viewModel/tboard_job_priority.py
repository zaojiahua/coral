from app.v1.tboard.viewModel.tborad import TBoardViewModel


class TBoardJobPriorityViewModel(TBoardViewModel):
    def __init__(self, *args, **kwargs):
        self.device_mapping = kwargs.get("device_mapping")
        kwargs["jobs"] = []
        kwargs["device_label_list"] = []
        super().__init__(*args, **kwargs)

    def add_dut_list(self, device_idle_list):
        dut_obj_list = []
        job_label_list = []
        for device_label in device_idle_list:
            for device_task in self.device_mapping:
                if device_label == device_task.get("device_label"):
                    job_label_list = [job["job_label"] for job in device_task.get("job")]
            dut_obj_list.append(self.add_dut(device_label, job_label_list, self.repeat_time, self.tboard_id))
        return dut_obj_list
