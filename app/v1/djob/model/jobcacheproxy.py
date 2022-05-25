import copy
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait
import random
import zipfile

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

    def __init__(self, jobs, tboard_path):
        self.jobs = jobs
        self.tboard_path = tboard_path

    def sync(self):
        job_syn_resource_massage = read_json_file(JOB_SYN_RESOURCE_MASSAGE)
        """
        {
            job_lable:updated_time,
            ...
        }
        """
        temp = copy.deepcopy(job_syn_resource_massage)
        update_json_content = copy.deepcopy(job_syn_resource_massage)
        update_job_list = []
        update_job_labels = []
        transition_inner_job = None

        # 优先下载inner job，优先解压
        def find_update_job_list(job, inner_job=False):
            job_label = job['job_label']
            if not os.path.exists(os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}.zip")) \
                    or job_syn_resource_massage.get(job_label) != job["updated_time"]:
                # 多个线程同时使用同一个文件，会报“另一个程序正在使用此文件，进程无法访问。”的错误，同时防止多次下载同一个资源
                if job_label not in update_job_labels:
                    if inner_job:
                        update_job_list.insert(0, job)
                    else:
                        update_job_list.append(job)
                    update_job_labels.append(job_label)
                    temp[job_label] = job["updated_time"]
                    return 1
            return 0

        for job in self.jobs:
            # 没有缓存的zip或zip需要更新
            find_update_job_list(job)
            if job.get("inner_job", []):
                for inner_job in job["inner_job"]:
                    is_find = find_update_job_list(inner_job, inner_job=True)
                    if transition_inner_job is None and is_find:
                        transition_inner_job = inner_job['job_label']
                        print('中间的inner job是:', transition_inner_job)

        # 判断所有文件是否成功
        sync_success = True
        # 开启的线程数不要太多
        step = 8
        for i in range(0, len(update_job_list), step):
            begin_index = i
            for j, update_job in enumerate(update_job_list[i:i + step]):
                # inner job 之前的先下载
                if transition_inner_job == update_job['job_label'] and j != (step - 1):
                    print('inner job 先下载')
                    all_task = [executer.submit(self.download, update_job, self.tboard_path) for update_job in
                                update_job_list[begin_index:begin_index + j + 1]]
                    wait(all_task)
                    begin_index = begin_index + j + 1
                    print('inner job 先下载的已经完成', begin_index)
                    break
            all_task = [executer.submit(self.download, update_job, self.tboard_path) for update_job in update_job_list[begin_index:i + step]]
            wait(all_task)

            # 根据是否下载下来更新json文件
            for task_result in all_task:
                download_result = task_result.result()
                if download_result != -1:
                    update_json_content[download_result] = temp[download_result]
                else:
                    # 虽然失败，但是下载好的包正常解压和写入文件
                    sync_success = False

        dump_json_file(update_json_content, JOB_SYN_RESOURCE_MASSAGE)
        return sync_success

    @staticmethod
    def download(job_msg, tboard_path):
        # 通过重试的方式解决异常，可能遇到的异常：1、多个tboard里边有相同的job或者inner job，虽然一个tboard做了去重，但是多个tboard并没有去重
        # 2、一次请求大量zip包的时候，部分线程request_file的时候，timeout以后才返回
        max_retry = 6
        retry = 0
        while retry <= max_retry:
            try:
                url = job_msg["url"]
                job_label = job_msg["job_label"]
                logger.info(f'正在下载的是: {url} {job_label}')
                job_msg_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}.zip")
                job_msg_temp_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job_label}_temp.zip")
                # 设置超时时间，否则会一直等待
                file_content = request_file(url, timeout=120)
                with open(job_msg_temp_name, "wb") as code:
                    code.write(file_content.content)
                if os.path.exists(job_msg_name):
                    os.remove(job_msg_name)
                os.rename(job_msg_temp_name, job_msg_name)
                # 下载完成
                logger.info(f'下载完成: {job_label}')

                # 开始解压，解压失败的话，有可能是下载过程中包不完整，所以重新下载
                JobCacheProxy.unzip_job(job_msg, tboard_path)
                # 解压完成
                logger.info(f'解压完成：{job_label}')
                return job_label
            except Exception as e:
                retry += 1
                if retry > max_retry:
                    logger.error('-----------------下载出错了--begin-----------')
                    logger.error(e)
                    logger.error('-----------------下载出错了----end---------')
                    return -1
                else:
                    # 为了防止多个线程同一时刻重试，同时，重试的次数越多，等待的时间也应该越多
                    retry_second = pow(2, retry) + (random.randint(0, 1000) / 1000)
                    logger.info(f'----------重试---------------{retry}---{retry_second}')
                    time.sleep(retry_second)

    @staticmethod
    def unzip_job(job, tboard_path):
        # 这里解压会遇到问题，子包还没有下载下来的话，解压子包就是用的旧包
        job_msg_name = os.path.join(JOB_SYN_RESOURCE_DIR, f"{job['job_label']}.zip")
        if not os.path.exists(os.path.join(tboard_path, job["job_label"])):
            logger.info(f'解压中----{job_msg_name}')
            with zipfile.ZipFile(job_msg_name, 'r') as zip_ref:
                zip_ref.extractall(os.path.join(tboard_path, job["job_label"]))
        if job.get("inner_job", []):
            for inner_job in job["inner_job"]:
                JobCacheProxy.unzip_job(inner_job, tboard_path)
