import os
import time
from concurrent.futures import ThreadPoolExecutor, wait

import requests

from app.config.url import job_url_filter
from app.libs.func_tools import async_timeout
from app.libs.http_client import _parse_url
from app.v1.Cuttle.boxSvc import box_init
from app.v1.cabinet_register import cabinet_register
from app.v1.djob import djob_flush
from app.libs.ospathutil import deal_dir_file

PROJECT_SIBLING_DIR = os.path.dirname((os.path.dirname(os.path.abspath(__file__))))


def server_init():
    check_reef_exist()
    # 不要删除数据库的内容，否则意外停止的任务不再运行了
    # redis_client.flushdb()

    # 删除老的日志文件，只保留上次的日志，再久的从来没有看过，还占用存储空间
    for dirname in os.listdir(os.path.join(PROJECT_SIBLING_DIR, "coral-log")):
        if dirname != 'log':
            deal_dir_file(os.path.join(PROJECT_SIBLING_DIR, "coral-log", dirname))

    try:
        log_path = os.path.join(PROJECT_SIBLING_DIR, "coral-log", "log")
        if os.path.exists(log_path):
            os.rename(log_path, log_path + f"_{time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())}")
        os.makedirs(log_path)
    except Exception:
        pass

    init_func = [
        cabinet_register,
        # tempr_init,
        # power_init,
        box_init,
        djob_flush,
    ]
    executor = ThreadPoolExecutor(len(init_func))
    all_task = [executor.submit(func) for func in init_func]
    wait(all_task)


@async_timeout(4 * 60)
def check_reef_exist():
    while requests.get(_parse_url(job_url_filter.format("?fields=id&job_deleted=False"))).status_code != 200:
        print("-------", requests.get(_parse_url(job_url_filter.format("?fields=id&job_deleted=False"))).status_code)
        print("in check reef exist ")
        time.sleep(1)
