import os
import platform

from .ip import *
from .post import *
from .secure import *

# log 必须导入
from .log import *

DEBUG = False

DEFAULT_DATE_TIME_FORMAT = "%Y_%m_%d_%H_%M_%S"
REEF_DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_DATE_FORMAT = "%Y_%m_%d"
DEFAULT_TIME_FORMAT = "%H_%M_%S"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_SIBLING_DIR = os.path.dirname(BASE_DIR)

LOG_DIR = os.path.join(PROJECT_SIBLING_DIR, "coral-log")

JOB_SYN_RESOURCE_DIR = os.path.join(PROJECT_SIBLING_DIR, "job_resource")

if not os.path.exists(JOB_SYN_RESOURCE_DIR):
    os.makedirs(JOB_SYN_RESOURCE_DIR)

JOB_SYN_RESOURCE_MASSAGE = os.path.join(JOB_SYN_RESOURCE_DIR, "massage.json")

if platform.system() == 'Linux':
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_IP}:6379/0"
else:
    from app.config.local import LOCAL_REDIS_URL

    REDIS_URL = LOCAL_REDIS_URL

REEF_URL = f"http://{REEF_IP}:{REEF_PORT}"

FAIL_PIC_NAME = "fail.png"
SUCCESS_PIC_NAME = "success.png"
LEAVE_PIC_NAME = "leave.png"
TEMP_TEST_INTERVAL = 5
# ADB_SERVER_NUM = 3

EXPOSE_HEADERS = "*"

AI_TESTER_INTERVAL = 180
BATTERY_CHECK_INTERVAL = 420
# ADB_MAPPING_DICT = {0: ADB_SERVER_1, 1: ADB_SERVER_2, 2: ADB_SERVER_3}


DEVICE_BRIGHTNESS = 227

# # try:
# #     from app.config.ip import CORAL_TYPE
# # except ImportError:
#     CORAL_TYPE = 1
try:
    CORAL_TYPE = CORAL_TYPE
except  NameError:
    CORAL_TYPE = 1
if platform.system() == 'Linux':
    if CORAL_TYPE == 3:
        HARDWARE_MAPPING_LIST = ['rotate']
    elif CORAL_TYPE == 4:
        HARDWARE_MAPPING_LIST = ['arm']
    else:
        HARDWARE_MAPPING_LIST = ['arm','1']
else:
    HARDWARE_MAPPING_LIST = ['COM9','1']
