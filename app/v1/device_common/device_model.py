import os.path
import time
import math
import traceback

from astra import models

from app.config.setting import ADB_TYPE, HOST_IP
from app.config.url import device_create_update_url, device_url, device_phone_model_coordinate, coordinate_url
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
from app.libs.extension.field import OwnerList
from app.config.setting import CORAL_TYPE
from app.v1.Cuttle.basic.setting import m_location_center, set_global_value, get_global_value, m_location, \
    COORDINATE_CONFIG_FILE, Z_DOWN
from app.v1.Cuttle.basic.basic_views import UnitFactory


class DeviceStatus(object):
    IDLE = 'idle'
    BUSY = 'busy'
    OCCUPIED = 'occupied'
    OFFLINE = 'offline'
    ERROR = 'error'


class Device(BaseModel):
    # attribute that only coral have
    exclude_list = ["src_list", "has_camera", "has_arm", "flag", "is_bind", "x_border", "y_border", "kx1", "kx2", "ky1",
                    "ky2", "assis_1", "assis_2", "assis_3", "x1", "x2", "y1", "y2", 'subsidiarydevice', 'disconnect_times_timestamp']
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
    # 这里的宽高是分辨率
    pix_width = models.IntegerField()
    pix_height = models.IntegerField()
    temp_port_list = models.Set()
    monitor_index = models.CharField()
    x_dpi = models.CharField()
    y_dpi = models.CharField()
    x_border = models.CharField()
    y_border = models.CharField()
    # 这里是用户输入的设备实际宽高厚度
    width = models.CharField()
    height = models.CharField()
    ply = models.CharField()
    screen_z = models.CharField()
    # 用户在设备地图页配置的所有点
    device_config_point = {}
    # attribute that only coral use
    is_bind = models.BooleanField()
    flag = models.BooleanField()
    has_arm = models.BooleanField()
    has_camera = models.BooleanField()
    has_rotate_arm = models.BooleanField()
    # 设备左上角点和右下角点的坐标（在摄像机模式下）
    x1 = models.CharField()
    y1 = models.CharField()
    x2 = models.CharField()
    y2 = models.CharField()
    # 摄像头下多个按键的位置,储存的是屏幕截图中的坐标（paneview设置&重启服务恢复设备时，需要读取数据库中存的摄像头的下坐标值，并换算回截图中的坐标值）
    back_x = models.CharField()
    back_y = models.CharField()
    back_z = models.CharField()
    home_x = models.CharField()
    home_y = models.CharField()
    home_z = models.CharField()
    menu_x = models.CharField()
    menu_y = models.CharField()
    menu_z = models.CharField()
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
    # 代表每次重连发生的时间
    disconnect_times_timestamp = OwnerList(to=int)
    # 僚机列表
    subsidiarydevice = OwnerList(to=str)
    # 如果是僚机，代表的是第几个僚机，0代表的就是主机
    order = models.IntegerField()

    float_list = ["x_dpi", "y_dpi", "x_border", "y_border", "x1", "x2", "y1", "y2",
                  'width', 'height', 'ply', "screen_z", 'back_x', 'back_y', 'back_z',
                  'home_x', 'home_y', 'home_z', 'menu_x', 'menu_y', 'menu_z']

    def __init__(self, *args, **kwargs):
        super(Device, self).__init__(*args, **kwargs)
        self.logger = setup_logger(f'{self.pk}', f'{self.pk}.log')
        self.flag = True

    def __repr__(self):
        return f"{self.__class__.__name__}_{self.pk}_{self.device_name}_{self.id}"

    # 获取当个设备的信息或者是获取所有设备的信息，所以是静态方法
    @staticmethod
    def request_device_info(device_label=None):
        common_fields = "id,auto_test,device_name,cpu_id,ip_address,status," \
                        "tempport,tempport.port,powerport,powerport.port,device_label,android_version," \
                        "android_version.version,monitor_index,monitor_index.port,phone_model.phone_model_name," \
                        "phone_model.x_border,phone_model.y_border,phone_model.cpu_name,phone_model.manufacturer," \
                        "phone_model.id,phone_model.x_dpi,phone_model.y_dpi,phone_model.manufacturer.manufacturer_name," \
                        "phone_model.width,phone_model.height,phone_model.ply," \
                        "phone_model.width_resolution,phone_model.height_resolution," \
                        "rom_version,rom_version.version,paneslot.paneview.type,paneslot.paneview.camera," \
                        "paneslot.paneview.id,paneslot.paneview.robot_arm," \
                        "subsidiarydevice.id,subsidiarydevice.serial_number,subsidiarydevice.order," \
                        "subsidiarydevice.phone_model.height_resolution,subsidiarydevice.phone_model.width_resolution," \
                        "subsidiarydevice.phone_model.phone_model_name"
        if device_label is None:
            param = {"status__in": "ReefList[idle{%,%}busy{%,%}error{%,%}occupied]",
                     "cabinet_id": HOST_IP.split(".")[-1],
                     "fields": common_fields}
        else:
            param = {'cabinet_id': HOST_IP.split(".")[-1],
                     'device_label': device_label,
                     'fields': common_fields}

        res_device_info = request(url=device_url, params=param)

        # 获取五型柜用户配置的坐标信息
        if math.floor(CORAL_TYPE) == 5:
            for device_dict in res_device_info.get("devices"):
                coors = request(url=device_phone_model_coordinate, params={'phone_model__device': device_dict['id'],
                                                                           'exclude': 'pk'})
                device_obj = Device(pk=device_dict['device_label'])
                for coor in coors.get('phonemodelcustomcoordinate', []):
                    coor_name = coor['name']
                    x = coor['x_coordinate']
                    y = coor['y_coordinate']
                    z = coor['z_coordinate']
                    device_obj.device_config_point[coor_name] = [x, y, z]
                    if coor_name == '桌面':
                        device_obj.home_x, device_obj.home_y, device_obj.home_z = x, y, z
                    elif coor_name == '返回':
                        device_obj.back_x, device_obj.back_y, device_obj.back_z = x, y, z
                    elif coor_name == '菜单':
                        device_obj.menu_x, device_obj.menu_y, device_obj.menu_z = x, y, z

        return res_device_info

    @property
    def device_height(self):
        if self.order == 0:
            return self.pix_height if math.floor(CORAL_TYPE) != 5 else (int(self.x2) - int(self.x1))
        else:
            return self.pix_height

    @property
    def device_width(self):
        # 区分主机和僚机
        if self.order == 0:
            return self.pix_width if math.floor(CORAL_TYPE) != 5 else (int(self.y2) - int(self.y1))
        else:
            return self.pix_width

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
            self.set_border(kwargs)
            self._update_pix_width_height(kwargs.get('phone_model', kwargs))
            self.kx1, self.ky1, self.kx2, self.ky2 = self._keyboard_relative_to_absolute(
                key_map_position.get(self.phone_model_name, default_key_map_position))
            self.update_subsidiary_device(**kwargs)
        except Exception as e:
            print(repr(e))
            print(traceback.format_exc())
            func(self, **kwargs)  # 4

    def remove_subsidiary_device(self):
        for _ in range(self.subsidiarydevice.llen()):
            old_serial_number = self.subsidiarydevice.lpop()
            Device(pk=old_serial_number).remove()

    # 更新僚机信息
    def update_subsidiary_device(self, **kwargs):
        # 先移除旧的
        self.remove_subsidiary_device()

        subsidiarydevice = kwargs.get('subsidiarydevice', [])
        print('僚机信息如下: ', subsidiarydevice)
        for sub_device in subsidiarydevice:
            serial_number = sub_device.get("serial_number")
            device_obj = Device(pk=serial_number)
            device_obj._update_pix_width_height(sub_device['phone_model'])
            device_obj.order = sub_device['order']
            device_obj.phone_model_name = sub_device['phone_model']['phone_model_name']
            device_obj.kx1, device_obj.ky1, device_obj.kx2, device_obj.ky2 = device_obj._keyboard_relative_to_absolute(
                key_map_position.get(device_obj.phone_model_name, default_key_map_position))
            self.subsidiarydevice.rpush(serial_number)

    # 获取僚机
    def get_subsidiary_device(self, order=None, serial_number=None):
        if serial_number is not None:
            for s_n in self.subsidiarydevice:
                if s_n == serial_number:
                    return Device(pk=serial_number)
        if order is not None:
            for s_n in self.subsidiarydevice:
                device_obj = Device(pk=s_n)
                if device_obj.order == order:
                    return device_obj
        return None

    def set_border(self, device_dict):
        # 设置roi区域
        if math.floor(CORAL_TYPE) == 5:
            if device_dict.get("paneslot") is not None \
                    and device_dict.get("paneslot").get("paneview") is not None:
                params = {
                    "pane_view": device_dict.get("paneslot").get("paneview").get("id"),
                    "phone_model": device_dict.get("phone_model").get("id")
                }
                res = request(url=coordinate_url, params=params)
                print('pane_view更新的情况是：', res, params)
                if len(res) < 1:
                    return

                self.update_device_border(res[0])
            else:
                self.x1 = 0
                self.y1 = 0
                self.x2 = 0
                self.y2 = 0
            print('设置的边框是:', self.x1, self.y1, self.x2, self.y2)

    # 键盘坐标转换的函数
    def _keyboard_relative_to_absolute(self, coordinate):
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

        self._set_char("width", kwargs, "phone_model", "width")
        self._set_char("height", kwargs, "phone_model", "height")
        self._set_char("ply", kwargs, "phone_model", "ply")

        kwargs["manufacturer"] = kwargs.pop("phone_model").get("manufacturer") if kwargs.get("phone_model") else ""
        self.manufacturer = kwargs.pop("manufacturer").get("manufacturer_name", "") if kwargs.get("manufacturer") else ""
        self.android_version = kwargs.pop("android_version").get("version", "") if kwargs.get("android_version") else ""
        self.rom_version = kwargs.pop("rom_version").get("version", "") if kwargs.get("rom_version") else ""
        self.monitor_index = kwargs.pop("monitor_index")[0].get("port", "") if kwargs.get("monitor_index") else ""
        for attr_name, attr_value in kwargs.items():
            if attr_name in self._astra_fields.keys() and not isinstance(attr_value, list):
                setattr(self, attr_name, attr_value)

        self._update_pix_width_height(kwargs)
        self.update_m_location()

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

    # 考虑到相机 像素宽高进行特殊的处理
    def _update_pix_width_height(self, kwargs):
        device_width = kwargs.get('width_resolution')
        device_height = kwargs.get('height_resolution')
        if device_width is not None:
            self.pix_width = device_width
        if device_height is not None:
            self.pix_height = device_height

    def update_device_border(self, data):
        # 设置roi
        self.x1 = str(int(data.get("inside_upper_left_x") or 0))
        self.y1 = str(int(data.get("inside_upper_left_y") or 0))
        self.x2 = str(int(data.get("inside_under_right_x") or 0))
        self.y2 = str(int(data.get("inside_under_right_y") or 0))

        return 0

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
        # 移除僚机信息
        self.remove_subsidiary_device()
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
        self.logger.debug(f'*************** url: {device_url}{self.id}/, status:{status}')

    # 更新5l机柜的m_location信息，没有机械臂对象，所以方法先写到这里
    def update_m_location(self):
        if CORAL_TYPE == 5.3:
            if not os.path.exists(COORDINATE_CONFIG_FILE):
                self.logger.error('多机械臂缺少必要的坐标配置文件, 请注意先配置坐标！！！')
            else:
                with open(COORDINATE_CONFIG_FILE, 'rt') as f:
                    for line in f.readlines():
                        key, value = line.strip('\n').split('=')
                        if key == 'm_location':
                            m_l = eval(value)
                            m_l.append(Z_DOWN)
                            set_global_value(key, m_l)
                        else:
                            set_global_value(key, eval(value))
        elif CORAL_TYPE == 5.1:
            set_global_value('m_location', [m_location_center[0] - float(self.width) / 2,
                                            m_location_center[1] - float(self.height) / 2,
                                            m_location_center[2] + float(self.ply)])
        else:
            set_global_value('m_location', [m_location[0], m_location[1], m_location[2] + (float(self.ply) if self.ply else 0)])
        self.screen_z = str(get_global_value('m_location')[2])
        set_global_value('Z_DOWN', get_global_value('m_location')[2])
        print('new Z_DOWN', get_global_value('Z_DOWN'))

    # 获取5l柜的点击坐标
    def get_click_position(self, x, y, z=0, roi=None, absolute=False, test=False):
        if roi is None:
            roi = [float(self.x1), float(self.y1), float(self.x2), float(self.y2)]

        m_location = get_global_value('m_location')

        if CORAL_TYPE == 5.3:
            dpi = get_global_value('pane_dpi')
            h, w, _ = get_global_value('merge_shape')
            if absolute:
                x = x + roi[1]
                y = y + w - roi[2]
                click_x = m_location[0] + x / dpi
                click_y = abs(m_location[1] - y / dpi)
                click_z = m_location[2] + float(z)
            else:
                # 从pane测试点击的时候走这里
                if not test:
                    x = float(x) * (roi[2] - roi[0]) + roi[0]
                    y = float(y) * (roi[3] - roi[1]) + roi[1]
                # 程序自己的测试走的这里
                click_x = m_location[0] + y / dpi
                click_y = abs(m_location[1] - (w - x) / dpi)
                click_z = m_location[2] + float(z)
        else:
            # 代表传入的x,y,z是以roi区域的左上角点为原点的，并且图片时经过旋转后的
            if absolute:
                x_location_per = x / (roi[3] - roi[1])
                y_location_per = y / (roi[2] - roi[0])
            else:
                # 先计算在相机拍照模式下 要点击的位置在roi的区域 计算出的百分比针对的是图片上的左上角点
                x_location_per = (1 - float(y))
                y_location_per = float(x)
            print('location percent ', x_location_per, y_location_per)
            # 然后对应实际的设备大小，换算成点击位置，要求roi必须和填入的设备宽高大小一致 注意拍成的照片是横屏还是竖屏 m_location针对的是实际的左上角点，其实是图片上的左下角点
            click_x = round((m_location[0] + float(self.width) * x_location_per), 2)
            click_y = round((m_location[1] + float(self.height) * y_location_per), 2)
            click_z = m_location[2] + float(z)

        return click_x, click_y, click_z

    # 将截图获取统一到这里
    def get_snapshot(self, image_path, high_exposure=False, original=False, connect_number=None,
                     max_retry_time=None, record_video=False, record_time=0, timeout=None, back_up_dq=None):
        jsdata = dict({"requestName": "AddaExecBlock", "execBlockName": "snap_shot",
                       "execCmdList": [f"adb -s {connect_number if connect_number is not None else self.connect_number} "
                                       f"exec-out screencap -p > {image_path}"],
                       "device_label": self.device_label,
                       'high_exposure': high_exposure,
                       'original': original,
                       'record_video': record_video,
                       'record_time': record_time,
                       'max_retry_time': max_retry_time,
                       'timeout': timeout,
                       'back_up_dq': back_up_dq})
        if self.has_camera and connect_number is None:
            handler_type = "CameraHandler"
        else:
            # 支持僚机截图
            handler_type = "AdbHandler"

        snap_shot_result = UnitFactory().create(handler_type, jsdata)
        return snap_shot_result.get('result')
