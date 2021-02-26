hand_serial_obj_dict = {}
hand_used_list = []
camera_dq_dict = {}
# 机械臂完全固定的参数
HAND_MAX_X = 315
HAND_MAX_Y = 245
Z_START = 4
Z_DOWN = -3.5
Z_UP = 8
MOVE_SPEED = 10000
SWIPE_TIME = 1
m_location = [42, 12]  # 机械臂下手机左上外边框在机械臂下的坐标
icon_threshold = 25
icon_threshold_camera = 10
icon_rate = 500

adb_disconnect_threshold = 15

last_swipe_end_point = (0,0)

color_threshold = 40
color_rate = 1500

BIAS = 0.237  # 机械臂下落--点击--抬起  所用时间。 更改硬件需要重新测量

Continues_Number = 1  # 连续多张判断准则，适用于性能测试
camera_w = 1280  # 摄像头拍摄分辨率，需要根据具体摄像头设置
camera_h = 720

chinese_ingore = 0.55

right_switch_percent = 0.87

CamObjList = []
normal_result = (False, None)
handler_config = {
    # 当复合unit中新增adb方法，需要更新此配置文件，指明其可能性
    "point": ("AdbHandler", "HandHandler"),
    "long_press": ("AdbHandler", "HandHandler"),
    "swipe": ("AdbHandler", "HandHandler"),
    "snap_shot": ("AdbHandler", "CameraHandler")
}
strip_str = '<>[]{}/",.\n、'
# imageTool排除干扰词
bounced_words = ["确定", "同意", "同意并继续", "同意并使用", "暂不开启", "允许", "好的", "开始", "继续","我知道了",
                 "跳过", "以后再说", "仅使用期间允许", "始终允许", "下一步", "暂不升级", "不了，谢谢", "知道了", "不开启",
                 "仅在使用此应用时允许"]
