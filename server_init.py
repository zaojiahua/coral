import os
import time
from concurrent.futures import ThreadPoolExecutor, wait

import requests

from app.config.url import job_url_filter
from app.libs.functools import async_timeout
from app.libs.http_client import _parse_url
from app.v1.Cuttle.boxSvc import box_init
from app.v1.cabinet_register import cabinet_register
from app.v1.djob import djob_init
from app.v1.tboard import tboard_init
from app.libs.ospathutil import deal_dir_file
from redis_init import redis_client

PROJECT_SIBLING_DIR = os.path.dirname((os.path.dirname(os.path.abspath(__file__))))

init_func = [
    cabinet_register,
    # tempr_init,
    # power_init,
    box_init,
    tboard_init,
    djob_init,
]


def server_init():
    check_reef_exist()
    redis_client.flushdb()

    # 删除老的日志文件，只保留上次的日志，再久的从来没有看过，还占用存储空间
    for dirname in os.listdir(os.path.join(PROJECT_SIBLING_DIR, "coral-log")):
        if dirname != 'log':
            deal_dir_file(os.path.join(PROJECT_SIBLING_DIR, "coral-log", dirname))

    log_path = os.path.join(PROJECT_SIBLING_DIR, "coral-log", "log")
    if os.path.exists(log_path):
        os.rename(log_path, log_path + f"_{time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())}")
    os.makedirs(log_path)

    executor = ThreadPoolExecutor(len(init_func))
    all_task = [executor.submit(func) for func in init_func]
    wait(all_task)


@async_timeout(4 * 60)
def check_reef_exist():
    while requests.get(_parse_url(job_url_filter.format("?fields=id&job_deleted=False"))).status_code != 200:
        print("-------", requests.get(_parse_url(job_url_filter.format("?fields=id&job_deleted=False"))).status_code)
        print("in check reef exist ")
        time.sleep(1)
