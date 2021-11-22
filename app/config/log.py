LOG_FORMAT = "[%(asctime)s][%(levelname)s][%(module)s:%(lineno)d][%(thread)d] - %(message)s"

LOG_ENABLED = True  # 是否开启日志
LOG_TO_CONSOLE = True  # 是否输出到控制台
LOG_TO_FILE = True  # 是否输出到文件

LOGGER_OBJ_DICT = {}  # 记录实例化的log 对象
# 8点以后的log保存到新的日志文件中
CRITICAL_HOUR = 8

TBOARD_LOG_NAME = "tboard"
DJOB_LOG_NAME = "djob"
TOTAL_LOG_NAME = "total"
IMG_LOG_NAME = "imgTool"
DOOR_LOG_NAME = "pane_door"
PANE_LOG_NAME = "pane"
NETWORK_LOG_NAME = "network"
REQUEST_LOG_TIME_STATISTICS = "request_log_time_statistics"
JOB_DOWNLOAD = "job_download"
