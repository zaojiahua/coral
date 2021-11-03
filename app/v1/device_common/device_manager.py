import os
import threading
import time

from app.libs.log import setup_logger
from redis_init import redis_client

device_process_list_filed = "device:process"
device_thread_list_filed = "device:thread:{}"
# 这个文件主要是用来对每个设备的线程做监控的，之前用来debug用，不涉及到业务逻辑逻辑

def add_device_thread_status(device_label):
    redis_client.sadd(device_process_list_filed, os.getpid())
    redis_client.hset(device_thread_list_filed.format(os.getpid()), device_label, threading.currentThread().ident)


def remove_device_thread_status(device_label):
    redis_client.hdel(device_thread_list_filed.format(os.getpid()), device_label)
    if not redis_client.exists(device_thread_list_filed.format(os.getpid())):
        redis_client.srem(device_process_list_filed, os.getpid())


def device_manager_loop():
    logger = setup_logger(f"deviceManager_{os.getpid()}", f'deviceManager_{os.getpid()}.log')
    logger.info(f"deviceManager_{os.getpid()} loop start")
    while True:  # 这里需要加一个分布式锁
        time.sleep(60 * 3)
        now_device_thread_list = {str(t.name) for t in threading.enumerate()}
        running_device_list = []
        finished_device_list = []
        for device_label, device_thread_id in redis_client.hgetall(
                device_thread_list_filed.format(os.getpid())).items():
            if device_label in now_device_thread_list:
                running_device_list.append(device_label)
            else:
                finished_device_list.append(device_label)

        #logger.info(f"device_thread running sum {len(running_device_list)}, list {running_device_list}")

        if finished_device_list:
            logger.error(f"device_thread finished sum {len(finished_device_list)}, list {finished_device_list}")
