import math

from app.config.setting import CORAL_TYPE
from redis_init import redis_client

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


# import的时候可能存在问题，所以变量都声明一下
m_location = None
m_location_center = None
Z_DOWN = None
Z_DOWN_1 = None  # Tcab-5D的右机械臂
ARM_MOVE_REGION = None
DOUBLE_ARM_MOVE_REGION = None
ARM_MAX_X = None
# 通过算法计算出来m_location
COMPUTE_M_LOCATION = True
if CORAL_TYPE == 5 or CORAL_TYPE == 5.2:
    # 5的升级版是中心对齐的
    try:
        from app.config.ip import m_location_center
    except ImportError:
        m_location_center = None
    try:
        from app.config.ip import m_location
    except ImportError:
        m_location = [38, 13, -24]  # Tcab-5现有夹具m_location
    set_global_value('m_location_original', m_location)
    set_global_value("m_location_center", m_location_center)
elif CORAL_TYPE == 5.1:
    try:
        from app.config.ip import m_location_center
    except ImportError:
        m_location_center = [157, 202.5, -24]
    set_global_value('m_location_center', m_location_center)
elif CORAL_TYPE == 5.3:
    try:
        from app.config.ip import ARM_MOVE_REGION, DOUBLE_ARM_MOVE_REGION, ARM_MAX_X
    except ImportError:
        ARM_MOVE_REGION = [201, 240]
        DOUBLE_ARM_MOVE_REGION = [365, 239]
        ARM_MAX_X = 340
elif math.floor(CORAL_TYPE) == 5:
    try:
        from app.config.ip import m_location_center
    except ImportError:
        m_location_center = [157, 202.5, -24]
    set_global_value('m_location_center', m_location_center)
try:
    from app.config.ip import COMPUTE_M_LOCATION
except ImportError:
    pass
try:
    from app.config.ip import Z_DOWN
    set_global_value('Z_DOWN_INIT', Z_DOWN)
    set_global_value('Z_DOWN', Z_DOWN)
except ImportError:
    raise Exception("ip.py文件异常，检查Z_DOWN值")

if CORAL_TYPE == 5.3:
    try:
        from app.config.ip import Z_DOWN_1
        set_global_value('Z_DOWN_1', Z_DOWN_1)
    except ImportError:
        set_global_value('Z_DOWN_1', Z_DOWN)

# 3c 同时有旋转机械臂和三轴机械臂，所以必须区分开来
hand_serial_obj_dict = {}
rotate_hand_serial_obj_dict = {}
hand_origin_cmd_prefix = 'Hand'
hand_used_list = []
camera_dq_dict = {}
sensor_serial_obj_dict = {}

# 相机的参数和柜子类型紧密相关，所以应该根据柜子类型来区分，而不是功能测试还是性能测试
# 因为不论功能测试，还是性能测试，用的相机硬件都是一样的
camera_params_5 = [("OffsetY", 0),
                   ("OffsetX", 0),
                   ("Width", 1440),
                   ("Height", 1080),
                   ("AcquisitionFrameRateEnable", True),
                   # ("ExposureTime", 3500.0),
                   ("Gain", 2.5),
                   # ('ADCBitDepth', 2, 'enum'),
                   ('BalanceWhiteAuto', 0, 'enum'),
                   ('BalanceRatioSelector', 0, 'enum'),
                   ('BalanceRatio', 1100),
                   ('BalanceRatioSelector', 1, 'enum'),
                   ('BalanceRatio', 950),
                   ('BalanceRatioSelector', 2, 'enum'),
                   ('BalanceRatio', 1850)]
# ("PixelFormat", 0x01080009, 'enum')]

if CORAL_TYPE == 5.2:
    # Tcab-5se进行功能测试的相机参数
    camera_params_5 = camera_params_5 + [('ADCBitDepth', 0, 'enum'),
                                         ("PixelFormat", 0x02180014, 'enum'),
                                         ("ExposureTime", 6000.0)]
else:
    camera_params_5 = camera_params_5 + [('ADCBitDepth', 2, 'enum'),
                                         ("PixelFormat", 0x01080009, 'enum'),
                                         ("ExposureTime", 3500.0)]

camera_params_50 = camera_params_5 + [("AcquisitionFrameRate", 200.0)]
# Tcab-5se功能测试使用的参数
camera_params_52 = camera_params_5 + [("AcquisitionFrameRate", 80.0),
                                      ('GammaEnable', True),
                                      ('Gamma', 0.7000)]
# Tcab-5se切换到性能测试时，相机需要修改的帧率相关参数
camera_params_52_performance = [('ADCBitDepth', 2, 'enum'),
                                ("PixelFormat", 0x01080009, 'enum'),
                                ("ExposureTime", 3500.0),
                                ("AcquisitionFrameRate", 200.0)]
camera_params_53 = camera_params_5 + [("AcquisitionFrameRate", 200.0)]
# 5L相机初始化参数
camera_params_51 = [("OffsetY", 0),
                    ("OffsetX", 0),
                    ("Width", 2448),
                    ("Height", 2048),
                    ("ExposureTime", 15000.0),
                    ("Gain", 2.5),
                    ("AcquisitionFrameRate", 60.0),
                    ("AcquisitionFrameRateEnable", True),
                    ("PixelFormat", 0x01080009, 'enum')]
# 5L改进版参数
# camera_params_51 = [("OffsetY", 0),
#                     ("OffsetX", 0),
#                     ("Width", 1440),
#                     ("Height", 1080),
#                     ("ExposureTime", 3500.0),
#                     ("Gain", 2.5),
#                     ("AcquisitionFrameRate", 240.0),
#                     ("AcquisitionFrameRateEnable", True),
#                     ("PixelFormat", 0x01080009, 'enum')]
camera_params_54 = [("OffsetY", 0),
                    ("OffsetX", 0),
                    ("Width", 720),
                    ("Height", 540),
                    ("ExposureTime", 2000.0),
                    ('ADCBitDepth', 2, 'enum'),
                    ("Gain", 2.5),
                    ("AcquisitionFrameRate", 320.0),
                    ("AcquisitionFrameRateEnable", True),
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
try:
    from app.config.ip import HAND_MAX_Y
except ImportError:
    if CORAL_TYPE == 5.2:
        HAND_MAX_Y = 245  # Tcab-5机械臂Y最大行程
    else:
        HAND_MAX_Y = 420  # 5L机械臂Y最大行程
HAND_MAX_Z = 5

if CORAL_TYPE == 5.3:
    # Z_UP = -22
    Z_UP = 0
    Z_START = -32
    arm_wait_position = f"G01 X0Y0Z{Z_UP}F15000 \r\n"
    HAND_MAX_X = DOUBLE_ARM_MOVE_REGION[0]
    HAND_MAX_Y = DOUBLE_ARM_MOVE_REGION[1]
else:
    Z_UP = 0
    Z_START = 0
    arm_wait_position = f"G01 X10Y-95Z{Z_UP}F15000 \r\n"

DIFF_X = 30
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
adb_disconnect_threshold = 20
# 和旋转机械臂相关
arm_default_y = '33'
arm_default = f"G01 X0Y{arm_default_y}Z0F5000 \r\n"
arm_move_position = f'G01 X0Y{arm_default_y}Z0F3000 \r\n'
# 和三轴机械臂相关
last_swipe_end_point = [0, 0]

color_threshold = 4000
color_rate = 1500

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

# 跟摄像机相关的参数
set_global_value('merge_image_h', None)  # 图片拼接的h矩阵
COORDINATE_CONFIG_FILE = 'app/config/coordinate.py'
MERGE_IMAGE_H = 'app/config/merge_image_h.npy'
CAMERA_IN_LOOP = 'camera_in_loop'  # 性能测试控制摄像机是否继续获取图片
set_global_value(CAMERA_IN_LOOP, False)

# 跟性能测试相关的参数
FpsMax = 240
for key in globals().get('camera_params_' + str(int(CORAL_TYPE * 10)), []):
    if key[0] == 'AcquisitionFrameRate':
        FpsMax = key[1]
        break
# 性能测试参数有可能单独设置
for key in globals().get('camera_params_' + str(int(CORAL_TYPE * 10)) + '_performance', []):
    if key[0] == 'AcquisitionFrameRate':
        FpsMax = key[1]
        break
if CORAL_TYPE == 5.1:
    CameraMax = int(FpsMax * 10)  # 5l可以拍10s
else:
    CameraMax = int(FpsMax * 7)  # 5系列其他相机拍5s
SWIPE_BIAS = int(FpsMax / 120 * (19 + 50))

click_loop_stop_flag = True  # 如果为True, 则停止多次点击
set_global_value("click_loop_stop_flag", click_loop_stop_flag)

# 相机外触发端子的指令
camera_power_open = "01050000ff008c3a"
camera_power_close = "010500000000cdca"
