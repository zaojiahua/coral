import os

from app.config.setting import PROJECT_SIBLING_DIR

# 运行时，job 资源文件存放地址
TBOARD_PATH = os.path.join(PROJECT_SIBLING_DIR, "Tboard") + os.sep
# 线程池大小
MAX_CONCURRENT_NUMBER = 256
STOP_DUT_MAX_ELAPSED_TIME = 30
