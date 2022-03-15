from app.v1.tboard.viewModel.tborad import TBoardViewModel


class TBoardJobPriorityViewModel(TBoardViewModel):
    def __init__(self, *args, **kwargs):
        self.device_mapping = kwargs.pop("device_mapping")
        job_obj_list = []
        for i in self.device_mapping:
            job_obj_list +=i.get("job")
        kwargs["jobs"] = job_obj_list
        kwargs["device_label_list"] = [i.get("device_label") for i in self.device_mapping]
        super().__init__(*args, **kwargs)

    def add_dut_list(self, device_idle_list):
        dut_obj_list = []
        job_label_list = []
        for device_label in device_idle_list:
            for device_task in self.device_mapping:
                if device_label == device_task.get("device_label"):
                    job_label_list = [job["job_label"] for job in device_task.get("job")]
            dut_obj_list.append(self.add_dut(device_label, job_label_list, self.repeat_time, self.tboard_id,
                                             self.job_random_order))
        return dut_obj_list
