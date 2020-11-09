from app.execption.outer.error_code.djob import JobExecBodyException
from app.v1.djob.config.setting import SWITCH_TYPE, NORMAL_TYPE, END_TYPE, FAILED_TYPE, INNER_DJOB_TYPE, SUCCESS_TYPE


class JobNode:
    def __init__(self, node_key, node_dict):
        self.node_key = node_key

        if node_dict is None:  # fail or end or success
            if node_key in [END_TYPE, FAILED_TYPE, SUCCESS_TYPE]:
                self.node_type = node_key
            else:
                raise JobExecBodyException(description=f"Unknown type {node_key}")
        else:
            self.node_type = node_dict["nodeType"]
            if SWITCH_TYPE == self.node_type:
                pass
            elif NORMAL_TYPE == self.node_type:
                self.exec_node_dict = node_dict["execDict"]
            elif INNER_DJOB_TYPE == self.node_type:
                self.job_label = node_dict["jobLabel"]
                self.assist_device_serial_number = node_dict.get("assistDevice", None)
            else:
                raise JobExecBodyException(description=f"Unknown type {self.node_type}")
