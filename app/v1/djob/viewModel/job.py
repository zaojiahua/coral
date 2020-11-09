import json
import logging
import os
import re
from functools import lru_cache

from app.config.log import JOB_DOWNLOAD
from app.config.url import job_url_filter
from app.execption.outer.error_code.djob import JobExecBodyException
from app.libs.http_client import request, request_file
from app.libs.jsonutil import read_json_file
from app.libs.log import setup_logger
from app.v1.djob.config.setting import START_TYPE, UI_JSON_FILE_NAME, JOB_FILE_PREFIX, NORMAL_TYPE
from app.v1.djob.model.job import Job
from app.v1.djob.viewModel.jobFormatTransferNewLinkNode import JobFormatTransform

"""
{
    "jobLinksDict": {
        "-2": {
            "0": {
                "nextNode": "-6"
            },
            "else": {
                "nextNode": "-5"
            }
        },
        "-3": {
            "nextNode": "-2"
        },
        "-6": {
            "nextNode": "end"
        },
        "start": "-3"
    },
    "jobNodesDict": {
        "-2": {
            "blockName": "isInCalendarApp",
            "checkDicFile": "isInCalendar",
            "nodeType": "switch"
        },
        "-3": {
            "execDict": {
                "blockName": "launchSystemCalendar",
                "unitLists": [
                    [...],
                    [...],
                    ...
                ]
            },
            "nodeType": "normal"
        },
        ...
    }
}

"""


# redis不存在 本地没有 status设置成1 ,下拉资源
# redis中存在 status 不为空 , get(job_path) == 1 表明正在更新，轮询等待，get(job_path) == 2 表明已经存在，获取资源
# status = redis_client.set(job_path, "1", nx=True)
@lru_cache(maxsize=128)
def get_job_exec_body(tboard_path, job_label):
    job_path = os.path.join(tboard_path, job_label) + os.sep
    ui_json_file_path = os.path.join(job_path, UI_JSON_FILE_NAME)

    if not os.path.exists(job_path):
        logging.getLogger(JOB_DOWNLOAD).error(f"the job {job_label} not download in tboard")
        os.makedirs(job_path)
        upload_job_res_file(job_path, job_label)
    exec_json = JobFormatTransform(read_json_file(ui_json_file_path)).jobDataFormat()
    return macro_repalce(exec_json, job_path)


def macro_repalce(exec_json_dict, job_path):
    res = json.dumps(exec_json_dict).replace(JOB_FILE_PREFIX, job_path)
    regex = re.compile(r'\\(?![/u"])')
    return json.loads(regex.sub(r"\\\\", res))


def upload_job_res_file(job_path, job_label):
    # 会抛异常 job 会捕获并返回result
    job_content = request(method="GET", url=job_url_filter.format(
        f"?fields=ui_json_file,job_res_file,job_res_file.name,job_res_file.file&job_label={job_label}"),
                          filter_unique_key=True)
    ui_file_content = request_file(job_content["ui_json_file"])
    with open(os.path.join(job_path, UI_JSON_FILE_NAME), "wb") as code:
        code.write(ui_file_content.content)

    for job_res_file in job_content["job_res_file"]:
        file_content = request_file(job_res_file["file"])
        with open(os.path.join(job_path, job_res_file["name"]), "wb") as code:
            code.write(file_content.content)


class JobViewModel:
    def __init__(self, job_label, tboard_path, **kwargs):
        self.assist_device_serial_number = kwargs.get("assist_device_serial_number")
        self.job_label = job_label
        self.tboard_path = tboard_path
        self.start_name = START_TYPE
        self.node_dict = None
        self.link_dict = None

    def to_model(self):
        self.init()
        return Job(**self.__dict__)

    def init(self):
        exec_job_body = get_job_exec_body(self.tboard_path, self.job_label)

        if exec_job_body.get("jobNodesDict", None) is None or exec_job_body.get("jobLinksDict", None) is None:
            raise JobExecBodyException(description=f"not this job {self.job_label}")

        self.node_dict = self.parse(exec_job_body.get("jobNodesDict", None))
        self.link_dict = exec_job_body.get("jobLinksDict", None)

        if self.start_name not in self.link_dict.keys():
            raise JobExecBodyException(description="job exec body lack of start")

    def parse(self, node_dict):
        # assist_device_serial_number不为空(为0)，表明使用inner_job
        # 向unit中添加僚机信息确保执行时使用僚机
        if self.assist_device_serial_number != 0:
            if isinstance(node_dict, dict):
                for idx, block in node_dict.items():
                    if block["nodeType"] == NORMAL_TYPE:
                        new_unit_lists = []
                        for unit_list in block.get("execDict", {}).get("unitLists"):
                            new_unit_list_dict = {"key": unit_list["key"], "unitList": []}
                            for unit in unit_list.get("unitList", []):
                                unit["assistDevice"] = self.assist_device_serial_number
                                new_unit_list_dict["unitList"].append(unit)
                            new_unit_lists.append(new_unit_list_dict)
                        node_dict[idx]["execDict"]["unitLists"] = new_unit_lists
        return node_dict


if __name__ == '__main__':
    from app.v1.tboard.config.setting import TBOARD_PATH

    tboard_path = os.path.join(TBOARD_PATH, "ssssss") + os.sep
    print(get_job_exec_body(tboard_path, "job-892f94d7-5bcf-4127-addd-89251a65ecbb"))
