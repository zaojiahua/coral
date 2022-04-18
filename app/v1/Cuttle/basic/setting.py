from app.config.setting import CORAL_TYPE
from redis_init import redis_client

try:
    from app.config.ip import m_location, m_location_center, Z_DOWN, ARM_MOVE_REGION, DOUBLE_ARM_MOVE_REGION
except Exception:
    m_location = [38, 13, -35]  # Tcab-5现有夹具m_location
    m_location_center = [157, 202.5, -24]
    if CORAL_TYPE == 5.2:
        m_location = [38, 13, -24]
    # Z_DOWN = -3.5   tianjing setting
    # Z_DOWN = -12   # 商米Tcab-5型柜夹具参数
    Z_DOWN = -27
    ARM_MOVE_REGION = [201, 240]
    DOUBLE_ARM_MOVE_REGION = [368, 239]

# 3c 同时有旋转机械臂和三轴机械臂，所以必须区分开来
hand_serial_obj_dict = {}
rotate_hand_serial_obj_dict = {}
hand_origin_cmd_prefix = 'Hand'
hand_used_list = []
camera_dq_dict = {}

# 相机的参数和柜子类型紧密相关，所以应该根据柜子类型来区分，而不是功能测试还是性能测试
# 因为不论功能测试，还是性能测试，用的相机硬件都是一样的
camera_params_50 = [("OffsetY", 0),
                    ("OffsetX", 0),
                    ("Width", 1440),
                    ("Height", 1080),
                    ("AcquisitionFrameRate", 170.0),
                    ("AcquisitionFrameRateEnable", True),
                    ("ExposureTime", 3500.0),
                    ("Gain", 2.5),
                    ('ADCBitDepth', 2, 'enum'),
                    ('BalanceWhiteAuto', 0, 'enum'),
                    ('BalanceRatioSelector', 0, 'enum'),
                    ('BalanceRatio', 1100),
                    ('BalanceRatioSelector', 1, 'enum'),
                    ('BalanceRatio', 950),
                    ('BalanceRatioSelector', 2, 'enum'),
                    ('BalanceRatio', 1850),
                    ("PixelFormat", 0x01080009, 'enum')]
camera_params_52 = camera_params_50 + [('GammaEnable', True), ('Gamma',  0.7000)]
camera_params_53 = camera_params_50
# 5L相机初始化参数
camera_params_51 = [("OffsetY", 0),
                    ("OffsetX", 0),
                    ("Width", 2448),
                    ("Height", 2048),
                    ("ExposureTime", 15000.0),
                    ("Gain", 2.5),
                    ("AcquisitionFrameRate", 35.0),
                    ('ADCBitDepth', 2),
                    ("PixelFormat", 0x01080009, 'enum')]

high_exposure_params = [("ExposureTime", 200000.0),
                        ("Gain", 15)]

# 俩个同步相机的参数
sync_camera_params = [('TriggerMode', 1, 'enum'),
                      ('TriggerSource', 0, 'enum'),
                      ('TriggerActivation', 2, 'enum'),
                      ('LineSelector', 0, 'enum')]

# 机械臂完全固定的参数
HAND_MAX_X = 315
if CORAL_TYPE == 5.1:
    HAND_MAX_Y = 420  # 5L机械臂Y最大行程
else:
    HAND_MAX_Y = 245  # Tcab-5机械臂Y最大行程
HAND_MAX_Z = 5
if CORAL_TYPE == 5.3:
    Z_UP = -32
    Z_START = -32
    arm_wait_position = f"G01 X0Y0Z{Z_UP}F15000 \r\n"
    HAND_MAX_X = DOUBLE_ARM_MOVE_REGION[0]
    HAND_MAX_Y = DOUBLE_ARM_MOVE_REGION[1]
else:
    Z_UP = 0
    Z_START = 0
    arm_wait_position = f"G01 X10Y-95Z{Z_UP}F15000 \r\n"

MOVE_SPEED = 15000
SWIPE_TIME = 1
# 按压侧边键参数
X_SIDE_KEY_OFFSET = 15
X_SIDE_OFFSET_DISTANCE = 5
PRESS_SIDE_KEY_SPEED = 3000
Z_SIDE = -30
Z_MIN_VALUE = -10
# 梯形滑动连带的比例
trapezoid = 0.9
wait_time = 1
icon_threshold = 30
icon_threshold_camera = 12
icon_rate = 500
icon_min_template = 0.005
icon_min_template_camera = 0.05
wait_bias = 1.1  # 从发给旋转机械臂-到触碰到开关键的时间补偿
adb_disconnect_threshold = 3
# 和旋转机械臂相关
arm_default_y = '33'
arm_default = f"G01 X0Y{arm_default_y}Z0F5000 \r\n"
arm_move_position = f'G01 X0Y{arm_default_y}Z0F3000 \r\n'
# 和三轴机械臂相关
last_swipe_end_point = [0, 0]

color_threshold = 4000
color_rate = 1500
g_bExit = False
# BIAS = 0.237  # 机械臂下落--点击--抬起  所用时间。 更改硬件需要重新测量
FpsMax = 240
CameraMax = 2400
BIAS = int(FpsMax / 120 * 19)  # 机械臂下落--点击--抬起  所用帧数。 更改硬件需要重新测量  31?
SWIPE_BIAS_HARD = int(FpsMax / 120 * 9)  # 机械臂下落--点击--抬起  所用帧数。 更改硬件需要重新测量  31?
SWIPE_BIAS = int(FpsMax / 120 * (19 + 50))

Continues_Number = 1  # 连续多张判断准则，适用于性能测试
camera_w = 1280  # 摄像头拍摄分辨率，需要根据具体摄像头设置
camera_h = 720

# 中文键盘忽略屏幕上半比例内文字
chinese_ingore = 0.55

# 屏幕右侧开关占比
right_switch_percent = 0.87

CamObjList = {}
normal_result = (False, None)
blur_signal = "[B]"
# 需要按常见顺序调整 亮度百分比的顺序 尽可能优先匹配到常见亮度变化。
light_pyramid_setting = [1, 0.4, 0.6, 1.4, 0.06, 0.1, 0.15, 0.2, 1.6, 1.8, 1.9, 2, 2.3]
light_pyramid_setting_simple = [0.1, 0.2, 0.4, 0.7, 1.3, 1.6, 1.8]

handler_config = {
    # 当复合unit中新增adb方法，需要更新此配置文件，指明其可能性
    "point": ("AdbHandler", "HandHandler"),
    "long_press": ("AdbHandler", "HandHandler"),
    "swipe": ("AdbHandler", "HandHandler"),
    "snap_shot": ("AdbHandler", "CameraHandler"),
    'bug_report': ('AdbHandler',)
}
strip_str = '<>[]{}/",.\n、'
# 特征词
serious_words = ['没有响应', '无响应']

adb_cmd_prefix = "adb "
KILL_SERVER = "kill-server"
START_SERVER = "start-server"
# 本来没有这条指令 但是为了让skill-server start-server作为一个原子操作，做一个这样的指令
RESTART_SERVER = 'restart-server'
SERVER_OPERATE_LOCK = 'server_operate_lock'
NORMAL_OPERATE_LOCK = 'normal_lock'

get_lock = '''
local is_exist = redis.call("GET", KEYS[1])
if is_exist then
    return 1
else
    redis.call("SET", ARGV[1], ARGV[2])
    return 0
end
'''
unlock = '''
local random_value = redis.call("GET", KEYS[1])
if random_value == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
'''

get_lock_cmd = redis_client.register_script(get_lock)
unlock_cmd = redis_client.register_script(unlock)

SCREENCAP_CMD = 'exec-out screencap -p >'
# 兼容更早的Android版本
SCREENCAP_CMD_EARLY_VERSION = "shell screencap -p | sed 's/\r$//' >"
SCREENCAP_CMD_VERSION_THRESHOLD = 6
FIND_APP_VERSION = 'versionName'
PM_DUMP = 'pm dump'

DEVICE_DETECT_ERROR_MAX_TIME = 30 * 60

_global_dict = {}


def set_global_value(key, value):
    """ 定义一个全局变量 """
    if key == 'm_location':
        print('new m_location:', value)
    _global_dict[key] = value


def get_global_value(key, def_value=None):
    try:
        return _global_dict[key]
    except KeyError:
        return def_value


set_global_value('m_location', m_location)
set_global_value('Z_DOWN', Z_DOWN)
# 图片拼接的h矩阵
set_global_value('merge_image_h', None)

PERFORMANCE_END_LOOP_TIMEOUT = 60 * 3
COORDINATE_CONFIG_FILE = 'app/config/coordinate.py'
MERGE_IMAGE_H = 'app/config/merge_image_h.npy'
