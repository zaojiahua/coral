hand_serial_obj_dict = {}
hand_used_list = []
camera_dq_dict = {}
camera_params = [("Width", 1280), ("Height", 720), ("OffsetY", 200), ("OffsetX", 0)]
camera_params_240 = [("Width", 1440), ("Height", 1080), ("OffsetY", 0), ("OffsetX", 0),("AcquisitionFrameRate",240.0),("ExposureTime",2500.0),("Gain",2.5)]

# 机械臂完全固定的参数
HAND_MAX_X = 315
HAND_MAX_Y = 245
Z_START = 0
# Z_DOWN = -3.5   tianjing setting
Z_DOWN = -27
Z_UP = 0
MOVE_SPEED = 15000
SWIPE_TIME = 1
# 梯形滑动连带的比例
trapezoid = 0.9
# m_location = [42, 12]  # 机械臂下手机左上外边框在机械臂下的坐标   tianjing setting
m_location = [38, 13]
wait_time = 1
icon_threshold = 30
icon_threshold_camera = 12
icon_rate = 500
icon_min_template = 0.005
icon_min_template_camera = 0.01
wait_bias = 1.1  # 从发给旋转机械臂-到触碰到开关键的时间补偿
adb_disconnect_threshold = 15
arm_default = "G01 X0Y33Z0F5000 \r\n"
arm_wait_position = f"G01 X10Y-95Z{Z_UP}F15000 \r\n"
last_swipe_end_point = [0, 0]

color_threshold = 40
color_rate = 1500
g_bExit = False
# BIAS = 0.237  # 机械臂下落--点击--抬起  所用时间。 更改硬件需要重新测量
FpsMax = 240
CameraMax = 1200
BIAS = int(FpsMax / 120 * 20)   # 机械臂下落--点击--抬起  所用帧数。 更改硬件需要重新测量  31?
SWIPE_BIAS_HARD = int(FpsMax / 120 * 9)  # 机械臂下落--点击--抬起  所用帧数。 更改硬件需要重新测量  31?
SWIPE_BIAS = int(FpsMax / 120 * (19+50))

Continues_Number = 1  # 连续多张判断准则，适用于性能测试
camera_w = 1280  # 摄像头拍摄分辨率，需要根据具体摄像头设置
camera_h = 720

# 中文键盘忽略屏幕上半比例内文字
chinese_ingore = 0.55

# 屏幕右侧开关占比
right_switch_percent = 0.87

CamObjList = []
normal_result = (False, None)
blur_signal = "[B]"

handler_config = {
    # 当复合unit中新增adb方法，需要更新此配置文件，指明其可能性

    "point": ("AdbHandler", "HandHandler"),
    "long_press": ("AdbHandler", "HandHandler"),
    "swipe": ("AdbHandler", "HandHandler"),
    "snap_shot": ("AdbHandler", "CameraHandler")
}
strip_str = '<>[]{}/",.\n、'
# imageTool排除干扰词
bounced_words = ["确定", "同意", "同意并继续", "同意并使用", "暂不开启", "允许", "好的", "开始", "继续", "我知道了",
                 "跳过", "以后再说", "仅使用期间允许", "仅在使用中允许","始终允许", "下一步", "暂不升级", "不了，谢谢", "知道了", "不开启",
                 "仅在使用此应用时允许"]
