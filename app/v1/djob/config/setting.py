import os

from app.config.setting import PROJECT_SIBLING_DIR
from app.execption.outer.error import APIException
from app.execption.outer.error_code.djob import JobExecUnknownException, JobExecBodyException
from app.execption.outer.error_code.imgtool import OcrRetryTooManyTimes
from app.execption.outer.error_code.total import RequestException

MACH_DUT_DATA_ROOT = os.path.join(PROJECT_SIBLING_DIR, "Pacific") + os.sep

# djob 工作路径
BASE_PATH = os.path.join(MACH_DUT_DATA_ROOT, "{device_label}", "{timestamp}") + os.sep
RDS_DATA_PATH_NAME = "rds"
DJOB_WORK_PATH_NAME = "djobwork"

RDS_INFO_DICT_FILE_NAME = "RdsInfo.json"

# Rds Info data dict keyNames
JOB_ID = "jobID"
JOB_END_DATETIME = "jobEndDateTime"
JOB_ASSESS_SCORE = "jobAssessScore"
JOB_ASSESS_DICT = "jobAssessDict"

# 下发的djob归属
TBOARD = "tboard"  # tboard下发的任务
DJOB = "djob"  # 内部下发的 innerjob


# 任务执行方式
SINGLE_SPLIT = "SingleSplit"  # 存在先后执行顺序，中间失败直接结束执行
FLOW_EXECUTE_MODE = [SINGLE_SPLIT]

# job node type
SWITCH_TYPE = "switch"
INNER_DJOB_TYPE = "job"
NORMAL_TYPE = "normal"
END_TYPE = "end"
SUCCESS_TYPE = "success"
FAILED_TYPE = "fail"
START_TYPE = "start"
ABNORMAL_TYPE = "Abnormal"
TERMINATE_TYPE = 'Terminate'

# unit setting
RESULT_TYPE = "#3AFFF3"  # 结果unit的标示

# job exec result
SUCCESS = 0
FAILED = 1
ABNORMAL = -111
TERMINATE = 2

# unit category
ADBC_TYPE = "ADBC"
TEMPER_TYPE = "TEMPER"
IMGTOOL_TYPE = "IMGTOOL"
COMPLEX_TYPE = "COMPLEX"

DJOB_QUEUE_MAX_LENGTH = 3
# job ui_json_file_name
UI_JSON_FILE_NAME = "ui.json"
# job file path replace
JOB_FILE_PREFIX = "<1ijobFile>"

# 针对以下 exception结果会推送error stack
ERROR_STACK = (
    JobExecBodyException.error_code,
    JobExecUnknownException.error_code,
    OcrRetryTooManyTimes.error_code,
    RequestException.error_code,
    APIException.error_code,
)

# job_assessment_value 为 1 的 APIEXCEPTION
# FAIL_API_EXCEPTION = (
#     EblockCannotFindFile,
# )

# job 最大retry次数
MAX_RETRY = 2

ERROR_FILE_DIR = os.path.join(MACH_DUT_DATA_ROOT, "error_file") + os.sep

if not os.path.exists(ERROR_FILE_DIR):
    os.makedirs(ERROR_FILE_DIR)
