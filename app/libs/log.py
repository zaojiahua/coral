import logging
import os

from app.config.log import NETWORK_LOG_NAME, REQUEST_LOG_TIME_STATISTICS, JOB_DOWNLOAD
from app.config.setting import LOG_FORMAT, LOG_TO_CONSOLE, LOG_TO_FILE, LOG_ENABLED, LOGGER_OBJ_DICT, TBOARD_LOG_NAME, \
    TOTAL_LOG_NAME, DJOB_LOG_NAME, IMG_LOG_NAME, LOG_DIR, DOOR_LOG_NAME, PANE_LOG_NAME
from app.libs.ospathutil import asure_path_exist


def setup_logger(logger_name, log_file, level=logging.DEBUG
                 , log_path=os.path.join(LOG_DIR, "log")):
    if LOGGER_OBJ_DICT.get(logger_name):
        return LOGGER_OBJ_DICT.get(logger_name)

    asure_path_exist(log_path)

    log_file_path = os.path.join(log_path, log_file)

    log_obj = logging.getLogger(logger_name)

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    log_obj.setLevel(level)

    if LOG_TO_CONSOLE:
        log_obj.addHandler(stream_handler)
    if LOG_TO_FILE:
        log_obj.addHandler(file_handler)

    LOGGER_OBJ_DICT[logger_name] = log_obj

    return log_obj


def logger_init():
    # server init exec
    if LOG_ENABLED:
        setup_logger(TBOARD_LOG_NAME, r'tboard.log')
        setup_logger(DJOB_LOG_NAME, r'djob.log')
        setup_logger(TOTAL_LOG_NAME, r'total.log')
        setup_logger(IMG_LOG_NAME, r'imgTool.log')
        setup_logger(DOOR_LOG_NAME, r'pane_door.log')
        setup_logger(PANE_LOG_NAME, r'pane.log')
        setup_logger(NETWORK_LOG_NAME, r'network.log')
        setup_logger(REQUEST_LOG_TIME_STATISTICS, r'request_log_time_statistics.log')
        setup_logger(JOB_DOWNLOAD, r'job_download.log')
