import logging
import os
import datetime

from app.config.setting import LOG_FORMAT, LOG_TO_CONSOLE, LOG_TO_FILE, LOGGER_OBJ_DICT, \
    LOG_DIR, CRITICAL_HOUR
from app.libs.ospathutil import asure_path_exist


# 不同的手机，不同的天数放到一个log文件中，方便查看
def setup_logger(logger_name, log_file, level=logging.DEBUG, log_path=os.path.join(LOG_DIR, "log")):
    last_time = LOGGER_OBJ_DICT.get(logger_name, {}).get('last_time')
    now = datetime.datetime.now()
    critical_time = datetime.datetime(year=now.year, month=now.month, day=now.day, hour=CRITICAL_HOUR)
    if last_time is None or (now > critical_time > last_time):
        # 先移除所有的handler
        old_log_obj = LOGGER_OBJ_DICT.get(logger_name, {}).get('log')
        if old_log_obj is not None:
            for h in old_log_obj.handlers:
                old_log_obj.removeHandler(h)
            del old_log_obj

        log_path = os.path.join(log_path, now.strftime('%Y_%m_%d'))
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

        LOGGER_OBJ_DICT[logger_name] = {'log': log_obj, 'last_time': now}

        return log_obj
    else:
        return LOGGER_OBJ_DICT.get(logger_name).get('log')
