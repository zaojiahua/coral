import logging
import os
import datetime
from logging import handlers

from app.config.setting import LOG_FORMAT, LOG_TO_CONSOLE, LOG_TO_FILE, LOGGER_OBJ_DICT, \
    LOG_DIR
from app.libs.ospathutil import asure_path_exist


# 不同的手机，不同的天数放到一个log文件中，方便查看
def setup_logger(logger_name, log_file, level=logging.DEBUG, log_path=os.path.join(LOG_DIR, "log"),
                 is_out_console=True):
    last_time = LOGGER_OBJ_DICT.get(logger_name, {}).get('last_time')
    now = datetime.datetime.now()
    if last_time is None:
        asure_path_exist(log_path)

        log_file_path = os.path.join(log_path, log_file)

        log_obj = logging.getLogger(logger_name)

        formatter = logging.Formatter(LOG_FORMAT)

        file_handler = handlers.TimedRotatingFileHandler(log_file_path, when='D', interval=1, encoding='utf-8')
        file_handler.suffix = "%Y_%m_%d.log"
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        log_obj.setLevel(level)

        if LOG_TO_CONSOLE and is_out_console:
            log_obj.addHandler(stream_handler)
        if LOG_TO_FILE:
            log_obj.addHandler(file_handler)

        LOGGER_OBJ_DICT[logger_name] = {'log': log_obj, 'last_time': now}

        return log_obj
    else:
        return LOGGER_OBJ_DICT.get(logger_name).get('log')
