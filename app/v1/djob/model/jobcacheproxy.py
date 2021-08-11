import copy
import os
import logging
from concurrent.futures import ThreadPoolExecutor, wait

from app.config.setting import JOB_SYN_RESOURCE_MASSAGE, JOB_SYN_RESOURCE_DIR
from app.libs.http_client import request_file
from app.libs.jsonutil import read_json_file, dump_json_file
from app.v1.tboard.config.setting import MAX_CONCURRENT_NUMBER
from app.config.log import TBOARD_LOG_NAME

executer = ThreadPoolExecutor(MAX_CONCURRENT_NUMBER)
logger = logging.getLogger(TBOARD_LOG_NAME)


class JobCacheProxy:
    """
    负责job 同步数据
    """
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
        update_job_labels = []

        def find_update_job_list(job):
            job_label = job['job_label']
            if not os.path.exists(os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}.zip")) \
                    or job_syn_resource_massage.get(job_label) != job["updated_time"]:
                # 多个线程同时使用同一个文件，会报“另一个程序正在使用此文件，进程无法访问。”的错误，同时防止多次下载同一个资源
                if job_label not in update_job_labels:
                    update_job_list.append(job)
                    update_job_labels.append(job_label)
                    temp[(job_label)] = job["updated_time"]

        for job in self.jobs:
            # 没有缓存的zip或zip需要更新
            find_update_job_list(job)
            if job.get("inner_job", []):
                for inner_job in job["inner_job"]:
                    find_update_job_list(inner_job)

        dump_json_file(temp, JOB_SYN_RESOURCE_MASSAGE)

        all_task = [executer.submit(self.download, update_job) for update_job in update_job_list]

        wait(all_task)

    def download(self, job_msg):
        try:
            url = job_msg["url"]
            job_label = job_msg["job_label"]
            logger.info(f'正在下载的是: {url} {job_label}')
            job_msg_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}.zip")
            job_msg_temp_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}_temp.zip")
            file_content = request_file(url)
            with open(job_msg_temp_name, "wb") as code:
                code.write(file_content.content)
            if os.path.exists(job_msg_name):
                os.remove(job_msg_name)
            os.rename(job_msg_temp_name, job_msg_name)
        except Exception as e:
            logger.error('-----------------下载出错了-------------')
            logger.error(e)
            logger.error('-----------------下载出错了-------------')
