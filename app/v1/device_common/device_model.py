import time

from astra import models

from app.config.ip import ADB_TYPE
from app.config.url import device_create_update_url, device_url
from app.libs.extension.model import BaseModel
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.operator.adb_operator import AdbHandler
from app.v1.Cuttle.boxSvc.box_views import get_port_temperature
from app.v1.device_common.device_manager import add_device_thread_status, remove_device_thread_status
from app.v1.device_common.setting import key_map_position, default_key_map_position
from app.v1.djob import DJobWorker
from app.v1.stew.model.aide_monitor import send_battery_check
from app.v1.tboard.model.dut import Dut
from app.execption.outer.error_code.djob import DeviceStatusError


# 设备状态
class DeviceStatus(object):
    IDLE = 'idle'
    BUSY = 'busy'
    OCCUPIED = 'occupied'
    OFFLINE = 'offline'
    ERROR = 'error'


class Device(BaseModel):
    # attribute that only coral have
    exclude_list = ["src_list", "has_camera", "has_arm", "flag", "is_bind", "x_border", "y_border", "kx1", "kx2", "ky1",
                    "ky2", "assis_1", "assis_2", "assis_3", "x1", "x2", "y1", "y2"]
    # device basic attribute
    device_label = models.CharField()
    ip_address = models.CharField()
    phone_model_name = models.CharField()
    android_version = models.CharField()
    rom_version = models.CharField()
    manufacturer = models.CharField()
    cpu_id = models.CharField()
    cpu_name = models.CharField()
    id = models.IntegerField()
    # device extra attribute
    device_name = models.CharField()
    auto_test = models.BooleanField()
    power_port = models.CharField()
    device_width = models.IntegerField()
    device_height = models.IntegerField()
    temp_port_list = models.Set()
    monitor_index = models.CharField()
    x_dpi = models.CharField()
    y_dpi = models.CharField()
    x_border = models.CharField()
    y_border = models.CharField()
    # attribute that only coral use
    is_bind = models.BooleanField()
    flag = models.BooleanField()
    has_arm = models.BooleanField()
    has_camera = models.BooleanField()
    has_rotate_arm = models.BooleanField()
    x1 = models.CharField()
    y1 = models.CharField()
    x2 = models.CharField()
    y2 = models.CharField()
    # 摄像头下多个按键的位置,储存的是屏幕截图中的坐标（paneview设置&重启服务恢复设备时，需要读取数据库中存的摄像头的下坐标值，并换算回截图中的坐标值）
    back_x = models.IntegerField()
    back_y = models.IntegerField()
    home_x = models.IntegerField()
    home_y = models.IntegerField()
    menu_x = models.IntegerField()
    menu_y = models.IntegerField()
    # 输入键盘的左上点和右下点
    kx1 = models.IntegerField()
    kx2 = models.IntegerField()
    ky1 = models.IntegerField()
    ky2 = models.IntegerField()
    assis_1 = models.CharField()
    assis_2 = models.CharField()
    assis_3 = models.CharField()
    # 代表设备状态
    status = models.CharField()
    # 代表重连次数
    disconnect_times = models.IntegerField()

    float_list = ["x_dpi", "y_dpi", "x_border", "y_border", "x1", "x2", "y1", "y2"]

    def __init__(self, *args, **kwargs):
        super(Device, self).__init__(*args, **kwargs)
        self.logger = setup_logger(f'{self.pk}', f'{self.pk}.log')
        self.flag = True

    def __repr__(self):
        return f"{self.__class__.__name__}_{self.pk}_{self.device_name}_{self.id}"


    @property
    def connect_number(self):
        return self.ip_address + ":5555" if ADB_TYPE == 0 else self.cpu_id

    @property
    def data(self):
        """
        get all attribute by dict format
        """
        data = dict()
        for key, value in self._astra_fields.items():
            # add more fields's type when changed
            if key not in self.exclude_list:
                if self.is_single_field(value):
                    if value._obtain():
                        if key in self.float_list:
                            data[key] = float(value._obtain())
                        else:
                            data[key] = value._obtain()
                else:
                    data[key] = [i for i in value.smembers()]
        return data

    def is_exist(self):
        """
        "ip" is thought as a key-attribute  to judge whether device exist
        """
        result = True if self.ip_address else False
        return result

    def _update_attr_default(self, **kwargs):
        """
        update device's attribute by a dict
        """
        for key, value in self._astra_fields.items():
            if self.is_single_field(value) and kwargs.get(key):
                setattr(self, key, kwargs.get(key))
            elif not self.is_single_field(value) and kwargs.get(key):
                if not isinstance(kwargs.get(key), list):
                    raise TypeError("Set fields only accept List ")
                setattr(self, key, None)
                getattr(self, key).sadd(kwargs.get(key))
        if "temp_port_list" in kwargs:
            kwargs["temp_port"] = self._astra_fields["temp_port_list"].smembers()
        request(method="POST", url=device_create_update_url, json=kwargs)

    def update_attr(self, func=_update_attr_default, **kwargs):
        self.logger.debug("update device attr-------------")
        # 1. device recover from reef when restart
        # 2. device register from paneDoor
        # 3. device set config from machPane(cedar)
        # 4. others
        try:
            if "ip_address" not in kwargs.keys():  # 3
                self._update_attr_from_cedar(**kwargs)
            elif "powerport" not in kwargs.keys():  # 2
                self._update_attr_from_device(**kwargs)
            else:
                self._update_attr_from_reef(**kwargs)  # 1
            if kwargs.get("avoid_push") is not True:
                request(method="POST", url=device_create_update_url, json=self.data)
            self.flag = True
            self.kx1, self.ky1, self.kx2, self.ky2 = self._relative_to_absolute(
                key_map_position.get(self.phone_model_name, default_key_map_position))
        except Exception as e:
            print(repr(e))
            func(self, **kwargs)  # 4

    def _relative_to_absolute(self, coordinate):
        if any((i < 1 for i in coordinate)):
            coordinate = int(self.device_width * coordinate[0]), int(self.device_height * coordinate[1]), int(
                self.device_width * coordinate[2]), int(self.device_height * coordinate[3])
        return coordinate

    def _update_attr_from_cedar(self, **kwargs):
        self.logger.info(f"add device resource info:{kwargs}")
        self.power_port = kwargs.pop("powerport").get("port", "") if kwargs.get("powerport") and kwargs.get(
            "powerport").get("port") else ""
        while self.temp_port_list.smembers():
            self.temp_port_list.spop()
        if kwargs.get("tempport"):
            temp_port_list = [temp_port.get("port") for temp_port in kwargs.get("tempport")]
            for port in temp_port_list:
                self.temp_port_list.sadd(port)
            kwargs.pop("tempport")
        self.auto_test = kwargs.pop("auto_test", False)
        return kwargs

    def _update_attr_from_reef(self, **kwargs):
        self.logger.info(f"receive device's data from reef:{kwargs}")
        kwargs = self._update_attr_from_cedar(**kwargs)
        self._set_char("phone_model_name", kwargs, "phone_model", "phone_model_name")
        self._set_char("cpu_name", kwargs, "phone_model", "cpu_name")
        self._set_char("x_dpi", kwargs, "phone_model", "x_dpi")
        self._set_char("y_dpi", kwargs, "phone_model", "y_dpi")

        self._set_char("x_border", kwargs, "phone_model", "x_border")
        self._set_char("y_border", kwargs, "phone_model", "y_border")

        kwargs["manufacturer"] = kwargs.pop("phone_model").get("manufacturer") if kwargs.get("phone_model") else ""
        self.manufacturer = kwargs.pop("manufacturer").get("manufacturer_name", "") if kwargs.get(
            "manufacturer") else ""
        self.android_version = kwargs.pop("android_version").get("version", "") if kwargs.get("android_version") else ""
        self.rom_version = kwargs.pop("rom_version").get("version", "") if kwargs.get("rom_version") else ""
        self.monitor_index = kwargs.pop("monitor_index")[0].get("port", "") if kwargs.get("monitor_index") else ""
        for attr_name, attr_value in kwargs.items():
            if attr_name in self._astra_fields.keys() and not isinstance(attr_value, list):
                setattr(self, attr_name, attr_value)

    def _set_char(self, attr_name, dict, *args):
        try:
            for key in args:
                dict = dict.get(key)
            setattr(self, attr_name, dict)
        except (KeyError, ValueError):
            setattr(self, attr_name, "")

    def _update_attr_from_device(self, **kwargs):
        self.logger.info(f"receive device's data from device:{kwargs}")
        for attr_name, attr_value in kwargs.items():
            if attr_name in self._astra_fields.keys() and not isinstance(attr_value, list):
                setattr(self, attr_name, attr_value)

    def update_device_border(self, data):
        # 更换摄像头时，这个函数会发生变化
        # usb：图片左上 == 手机的左下 == 机械臂的左下
        # 海康： 图片左上== 手机右上  == 机械臂右上
        # 海康用1280*720  手机1920*1080
        # y_border_camera_pixel = (float(data.get("inside_upper_left_x")) - float(data.get("outside_upper_left_x"))) * (
        #         self.device_height / camera_w)
        # x_border_camera_pixel = (float(data.get("outside_under_right_y")) - float(data.get("inside_under_right_y"))) * (
        #         self.device_width / camera_h)
        # print(y_border_camera_pixel,x_border_camera_pixel)
        # x_camera_pixel = float(data.get("inside_under_right_y")) - float(data.get("inside_upper_left_y"))
        # y_camera_pixel = float(data.get("inside_under_right_x")) - float(data.get("inside_upper_left_x"))
        # if y_border_camera_pixel < 0 or x_border_camera_pixel < 0:
        #     return -1
        # x_real = 25.4 * self.device_width / float(self.x_dpi)
        # y_real = 25.4 * self.device_height / float(self.y_dpi)
        # print("x_real,y_real:",x_real,y_real)
        # self.x_border = str(round(x_border_camera_pixel * (x_real / x_camera_pixel), 2))
        # self.y_border = str(round(y_border_camera_pixel * (y_real / y_camera_pixel), 2))
        # print("border from camera。。。",self.x_border,self.y_border)

        #
        def cam_pix_to_scr(x, y, width):
            # 把摄像头下的坐标值，先转换成屏幕截图下的对应坐标值
            s_x = int((data.get("inside_under_right_y") - y) * (self.device_height / width))
            s_y = int((x - data.get("inside_upper_left_x")) * (self.device_height / width))
            return s_x, s_y

        width = int(data.get("inside_under_right_x") - data.get("inside_upper_left_x"))
        self.back_x, self.back_y = cam_pix_to_scr(data.get("return_x"), data.get("return_y"), width)
        self.menu_x, self.menu_y = cam_pix_to_scr(data.get("menu_x"), data.get("menu_y"), width)
        self.home_x, self.home_y = cam_pix_to_scr(data.get("desktop_x"), data.get("desktop_y"), width)
        # 下面是之前的代码  好像没用了.....
        self.x1 = str(int(data.get("inside_upper_left_x")))
        self.y1 = str(int(data.get("inside_under_right_y")))
        self.x2 = str(int(data.get("inside_under_right_x")))
        self.y2 = str(int(data.get("inside_upper_left_y")))
        return 0
        # usb 像头
        # y_border = data.get("inside_upper_left_x") - data.get("outside_upper_left_x")
        # x_border = data.get("inside_upper_left_y") - data.get("outside_upper_left_y")
        # if y_border < 0 or x_border < 0:
        #     return -1
        # self.x_border = str(round(x_border, 2))
        # self.y_border = str(round(y_border, 2))
        # self.x1 = str(data.get("inside_upper_left_x"))
        # self.y1 = str(data.get("inside_upper_left_y"))
        # self.x2 = str(data.get("inside_under_right_x"))
        # self.y2 = str(data.get("inside_under_right_y"))
        # return 0

    def to_str(self, number):
        float(number)

    @staticmethod
    def is_single_field(value):
        field_type = False if isinstance(value, models.Set) else True
        return field_type

    def simple_remove(self):
        """
        simplify the remove process(not use hash)
        """
        self.logger.warning(f"remove device info ")
        remove_device_thread_status(self.device_label)
        if self.ip_address != "0.0.0.0":
            h = AdbHandler(model=self)
            h.disconnect()
        self.remove()
        self.flag = False

    def start_device_sequence_loop(self, aide_monitor_instance):
        # 每一个设备拥有自己的同步循环loop，优先处理下发的任务，没有下发任务且auto test开启时执行推荐任务。
        self.logger.info(f"new device {self.device_label} into sequence_loop")
        # ------------------------Loop------------------------
        add_device_thread_status(self.device_label)
        while self.flag:
            time.sleep(2)
            # first priority do single djob
            try:
                if Dut.all(device_label=self.device_label):
                    DJobWorker(self.device_label).djob_process()
                # second send aitester's job
                elif self.auto_test:
                    # 上边的if不用加，因为add的地方进行了限制，如果加了的话，可能导致已经add，但是却没有执行的bug。
                    if self.status == DeviceStatus.ERROR:
                        continue
                    aide_monitor_instance.start_job_recommend()
            except Exception as e:
                self.logger.exception(f"Exception in sequence_loop: {repr(e)}")
                self.logger.error(f"Exception in sequence_loop: {repr(e)}")
        self.logger.warning(f"--flag changed in loop--：{self.flag}")

    def start_device_async_loop(self, aide_monitor_instance):
        # start battery auto-charging and temp auto-management asynchronously
        while self.flag:
            time.sleep(2)
            if self.status == DeviceStatus.ERROR:
                continue
            try:
                if self.power_port:
                    aide_monitor_instance.start_battery_management()
                if self.temp_port_list.smembers():
                    get_port_temperature(self.temp_port_list.smembers())
                send_battery_check(self.device_label, self.connect_number)
            except Exception as e:
                self.logger.error(f"Exception in async_loop: {repr(e)}")
        self.logger.warning(f"--flag changed--：{self.flag}")

    def is_device_error(self):
        if self.status == DeviceStatus.ERROR:
            raise DeviceStatusError()

    def update_device_status(self, status):
        request(method="PATCH", url=f'{device_url}{self.id}/', json={"status": status})
        self.status = status
