import copy
import os
from concurrent.futures import ThreadPoolExecutor, wait

from app.config.setting import JOB_SYN_RESOURCE_MASSAGE, JOB_SYN_RESOURCE_DIR
from app.libs.http_client import request_file
from app.libs.jsonutil import read_json_file, dump_json_file
from app.v1.tboard.config.setting import MAX_CONCURRENT_NUMBER

executer = ThreadPoolExecutor(MAX_CONCURRENT_NUMBER)


class JobCacheProxy:
    def __init__(self, jobs):
        self.jobs = jobs

    def sync(self):
        job_syn_resource_massage = read_json_file(JOB_SYN_RESOURCE_MASSAGE)
        """
        {
            job_lable:updated_time,
            ...
        }
        """
        temp = copy.deepcopy(job_syn_resource_massage)
        update_job_list = []

        for job in self.jobs:
            if job_syn_resource_massage.get(job["job_label"]) != job["updated_time"]:
                update_job_list.append(job)
                temp[(job["job_label"])] = job["updated_time"]
            if job.get("inner_job", []):
                for inner_job in job["inner_job"]:
                    if job_syn_resource_massage.get(inner_job["job_label"]) != inner_job["updated_time"]:
                        update_job_list.append(inner_job)
                        temp[(inner_job["job_label"])] = inner_job["updated_time"]

        dump_json_file(temp, JOB_SYN_RESOURCE_MASSAGE)

        all_task = [executer.submit(self.download, update_job) for update_job in update_job_list]

        wait(all_task)

    def download(self, job_msg):
        url = job_msg["url"]
        job_label = job_msg["job_label"]
        job_msg_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}.zip")
        job_msg_temp_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}_temp.zip")
        file_content = request_file(url)
        with open(job_msg_temp_name, "wb") as code:
            code.write(file_content.content)
        if os.path.exists(job_msg_name):
            os.remove(job_msg_name)
        os.rename(job_msg_temp_name, job_msg_name)
