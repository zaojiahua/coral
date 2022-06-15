import os
import platform
import sys

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

try:
    CORAL_TYPE = CORAL_TYPE
except NameError:
    CORAL_TYPE = 1

CORAL_TYPE_NAME = {
    1: 'Tcab_1',
    2: 'Tcab_2',
    3: 'Tcab_3',
    4: 'Tcab_4',
    5: 'Tcab_5',
    3.1: 'Tcab_3C',
    5.1: 'Tcab_5L',
    5.2: 'Tcab_5se',
    5.3: 'Tcab_5D',
    5.4: 'Tcab_5pro'
}

arm_com = os.environ.get('ARM_COM', '/dev/arm')
arm_com_1 = os.environ.get('ARM_COM_1', '/dev/arm_1')
# 命名的时候和arm_com统一
arm_com_sensor = os.environ.get('ARM_COM_SENSOR', '/dev/arm_sensor')
arm_com_1_sensor = os.environ.get('ARM_COM_1_SENSOR', '/dev/arm_sensor_1')
rotate_com = os.environ.get('ROTATE_COM', '/dev/rotate')
usb_power_com = os.environ.get("USB_COM", '/dev/USBPower')
camera_power_com = os.environ.get('CAMERA_COM', '/dev/CameraPower')

if CORAL_TYPE == 3:
    HARDWARE_MAPPING_LIST = [rotate_com]
elif CORAL_TYPE == 3.1:
    HARDWARE_MAPPING_LIST = [rotate_com, arm_com]
elif CORAL_TYPE == 4:
    HARDWARE_MAPPING_LIST = [arm_com]
elif CORAL_TYPE == 5.3:
    HARDWARE_MAPPING_LIST = ['1', '2', arm_com, arm_com_1, arm_com_sensor]
elif CORAL_TYPE == 5.4:
    HARDWARE_MAPPING_LIST = ['1', '2', arm_com, arm_com_sensor]
else:
    HARDWARE_MAPPING_LIST = ['1', arm_com, arm_com_sensor]

Bugreport_file_name = "bugreport.zip"

PICTURE_COMPRESS_RATIO = 0.5

if sys.platform.startswith("win"):
    find_command = "findstr"
else:
    find_command = "grep"

ERROR_CODE_FILE = 'error_code.csv'