import logging

from app.config.log import TOTAL_LOG_NAME

logger = logging.getLogger(TOTAL_LOG_NAME)


def executor_callback(worker):
    """
    检测Thread 执行过程是否失败,失败打印信息
    :param worker:
    :return:
    """
    print(worker.result)
    worker_exception = worker.exception()
    if worker_exception:
        logger.exception("Worker return exception: {}".format(worker_exception))
