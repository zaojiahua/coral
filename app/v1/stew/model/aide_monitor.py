import os
import random
from datetime import datetime, timedelta

import func_timeout
import numpy

from app.config.setting import PROJECT_SIBLING_DIR
from app.config.url import rds_url, job_url, device_power_url, device_temper_url, insert_tboard_url, device_url
from app.execption.outer.error import APIException
from app.execption.outer.error_code.stew import GetResourceFail
from app.libs.functools import execute_limit
from app.libs.http_client import request
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.basic_views import UnitFactory
from app.v1.Cuttle.boxSvc.box_views import on_or_off_singal_port
from app.v1.stew.setting import battery_data_amount
from app.v1.tboard.views.stop_specific_device import stop_specific_device


@execute_limit(60)
def send_battery_check(device_label, device_ip):
    try:
        # 此处只负责下发检测电量的adb指令，在adb operator里会根据结果解析具体电量数据。
        work_path = os.path.join(PROJECT_SIBLING_DIR, "Pacific", device_label, "djobBattery", )
        if not os.path.exists(work_path):
            os.makedirs(work_path)
        cmd_list = [
            #  todo 等产品确认编辑用例通信方式有线/无线
            f"adb  -s {device_ip} shell cat sys/class/power_supply/battery/capacity sys/class/power_supply/battery/status && echo battery mark || echo battery fail mark",
            # f'adb  -s {device_ip}:5555 shell dumpsys battery > {os.path.join(work_path,"battery.dat")}',
            # f"adb -s {device_ip} shell sleep 12"
        ]
        # f'adb  -s {device_ip}:5555 shell dumpsys batterystats >> {os.path.join(work_path,"battery.dat")}']
        jsdata = {}
        jsdata["ip_address"] = device_ip
        jsdata["device_label"] = device_label
        jsdata["execCmdList"] = cmd_list
        jsdata['max_retry_time'] = 1
        UnitFactory().create("AdbHandler", jsdata)
    except func_timeout.exceptions.FunctionTimedOut as e:
        pass

    return 0


class AideMonitor(object):
    _default = {
        "rest_time": 180,
        "check_n": 300,
        "check_h": 8
    }

    def __init__(self, device_object, rest_time=300):
        self.__dict__.update(self._default)
        self.jobPriorityDict = {}
        from app.v1.stew.init import similarity_matrix_monitor_object, user_id
        self.matrixMonitor = similarity_matrix_monitor_object
        self.ranking_job_list = None
        self.rest_time = rest_time
        self.user_id = str(user_id)
        self.temp_alarm = 50
        self.device_object = device_object
        self.logger = setup_logger(f'stew{device_object.pk}', f'stew-{device_object.pk}.log')

    @classmethod
    def get_defaults(cls, attr):
        if attr in cls._default:
            return cls._default[attr]
        else:
            return "do not have this attr name" + attr

    @execute_limit(600)
    def start_job_recommend(self):
        response = request(url=device_url, params={"id": self.device_object.id, "fields": "status"},filter_unique_key=True)
        if response.get("status") == "busy":
            return
        self.logger.info("start job recommend for one turn")
        rds_data = self.check_rds_data(
            device__id=self.device_object.id,
            end_time__lt=str(datetime.now()),
            start_time__gt=str(datetime.now() - timedelta(hours=self.check_h)),
            ordering="-id")
        self.logger.warning("[bug point0]")
        if not isinstance(rds_data, dict):
            self.logger.error("get a wrong response from reef when check rds in JobAllocateMonitor")
            raise GetResourceFail(description="get rds data from reef fail ")
        decision = self.process_data(rds_data)
        self.logger.debug(f"decision is {decision} in JobAllocateMonitor")
        self.do_action(decision)
        self.logger.info("already finished ones job recommend")

    def process_data(self, rds_data):
        # return job_id by given rds_data
        if len(rds_data.get("rdss", None)) <= self.check_n:
            self.logger.warning(f"rds data insufficient{len(rds_data.get('rdss'))},ready to calculate job list")
            return self.get_calculated_job_list()
        recent_rds_list = rds_data.get("rdss")
        self.logger.info(f"[bug point1]")
        recent_rds_assessment_list = [rds.get("job_assessment_value") for rds in recent_rds_list]
        if not "0" in recent_rds_assessment_list:
            # todo alarm to front
            self.logger.warning(
                f"find a abnormal device which have never finished a success job :{self.device_object.device_label} try to find_suitable_job in matrixMonitor get_calculated_job_list")
            return self.get_calculated_job_list()
        alternativeList = []
        random.shuffle(recent_rds_list)
        self.logger.info(f"[bug point2]")
        for rds in recent_rds_list:  # pri1 choose the job which both have success and fail record
            if rds.get("job_assessment_value") == "0":
                alternativeList.append(rds.get("job").get("id"))
            else:
                if rds.get("job").get("id") in alternativeList:
                    return rds.get("job").get("job_label", -2)
        return self.get_calculated_job_list()

    def get_calculated_job_list(self):
        try:
            if not self.ranking_job_list or self.ranking_job_list == -1:
                deviceAttributeDict = {
                    "phone_models": self.device_object.phone_model_name,
                    "android_version": self.device_object.android_version
                }
                filted_matrix, back_up_job_list = self.matrixMonitor.find_suitable_job(**deviceAttributeDict)
                self.logger.info(f"[bug point3] get back_up_job_list :{back_up_job_list}")
                self.ranking_job_list = self.matrixMonitor.calSpecificValue(self.device_object.device_label,
                                                                            filted_matrix,
                                                                            back_up_job_list)
                if self.ranking_job_list == -1:
                    return -1
                return self.ranking_job_list.pop(0)
            else:
                return self.ranking_job_list.pop(0)
        except Exception as e:
            self.logger.error("something wrong with auto recommend job list" + repr(e))
            return -1

    def do_action(self, job_label):
        if job_label == -1:  # fail to calculate job_label run random
            job_dict = self.check_job_data(fields="job_label", job_deleted=False)
            all_job_list = [i.get("job_label") for i in job_dict.get("jobs")]
            random_job_label = random.choice(all_job_list)
            self.send_tboard(random_job_label)
        else:
            self.logger.debug(f"find suitable job:{job_label},now send to run ")
            self.send_tboard(job_label)
        return 0

    def send_tboard(self, job_label):
        request_body = {
            "device_label_list": [self.device_object.device_label],
            "job_label_list": [job_label],
            "repeat_time": 1,
            "owner_label": self.user_id,
            "board_name": "Ai-job",
            "create_level": "AI_TEST"
        }
        self.logger.debug(f"ready to call tborad api,data:{request_body}")
        try:
            request(method="POST", url=insert_tboard_url, json=request_body)
        except APIException as e:
            self.logger.error(f"AI's tboard execute fail description:{e.description},error_code:{e.error_code}")

    @staticmethod
    def check_rds_data(*args, **kwargs):
        if not "fields" in kwargs.keys():
            kwargs["fields"] = "id,job_assessment_value,job,job.id,job.job_label,start_time,end_time"
        return request(method="GET", url=rds_url, params=kwargs)

    @staticmethod
    def check_job_data(**kwargs):
        if not "fields" in kwargs.keys():
            kwargs["fields"] = "job_label"
            kwargs["job_deleted"] = False
        return request(method="GET", url=job_url, params=kwargs)

    # ------------------------------------------------------------------------------------------------
    @execute_limit(300)
    def start_battery_management(self):
        try:
            self.logger.info(f"start battery management ones for {self.device_object.device_label}")
            battery_date = self.check_battery_data(self.device_object.id, dataAmount=battery_data_amount)
            if not battery_date.get("devicepowers"):
                self.logger.warning("do not find battery date in database ")
                return None
            battery_date = self.battery_data_transform(battery_date)
            judge_result = self.judge_4_charge(battery_date)
            self.do_action_for_battery(judge_result)
            self.logger.info("already finished battery monitor ones")
        except Exception as e:
            self.logger.warning(f"exception happened in battery_management:{repr(e)}")

    def check_battery_data(self, deviceID, dataAmount):
        # todo add dataAmount when reef support control data amount
        params = {
            "fields": "id,battery_level,charging,record_datetime",
            "record_datetime__gt": str(datetime.now() - timedelta(hours=12)),
            "record_datetime__lt": str(datetime.now()),
            "device__id": deviceID,
            "ordering": "-id"
        }
        return request(url=device_power_url, params=params)

    def battery_data_transform(self, battery_data):
        """
        :param battery_data:
        :return: ([95,90,85,70],["2018-10-10 13:11:11","","",""])
        """
        if int(battery_data.get("devicepowers")[0].get("battery_level")) >= 100:
            self.logger.debug(f"battery is already full for device:{self.device_object.pk} ")
            self.do_action_for_battery(False)
        elif int(battery_data.get("devicepowers")[0].get("battery_level")) <= 30:
            self.logger.debug(f"battery lower than 30% for device:{self.device_object.pk} ")
            self.do_action_for_battery(True)
        battery_list = []
        time_list = []
        for battery_data in battery_data.get("devicepowers", ""):
            if battery_data.get("charging", "") == False:
                battery_list.append(battery_data.get("battery_level", ""))
                time_list.append(battery_data.get("record_datetime", ""))
            else:
                break
        return (battery_list, time_list)

    def  judge_4_charge(self, battery_data):
        """
        :return: 1 -->charge  0--> uncharge
        """
        print("获取到的电量: ", battery_data)
        if len(battery_data[0]) < battery_data_amount:
            result = 2
        else:
            time_list = [round(int(i[8:10]) * 24 + int(i[11:13]) + float(i[14:16]) / 60, 3) for i in battery_data[1]]
            print("time_list：", time_list)
            z = numpy.polyfit(time_list, battery_data[0], 1)  # (x:h,y:battery%)  z:[k,b]
            print("z: ", z)
            k = round(float(z[0]), 3) + 0.0000001  # add bias 0.0000001 to prevent division by zero
            print("k: ", k)
            self.logger.debug(
                f"k value in calculate power:{k} for device:{self.device_object.pk} recent power data:{battery_data[0][0]}")
            result = 1 if -k >= 28 else 2
        return result

    def do_action_for_battery(self, judge_result):
        self.logger.debug(f"do_action_for_battery:{judge_result}")
        if judge_result == 2:
            return
        return on_or_off_singal_port({
            "port": self.device_object.power_port,
            "action": judge_result
        })

    # -------------------------------------------------------------------------
    @execute_limit(300)
    def start_temper_management(self):
        self.logger.info("start temper management thread...")
        temper_date = self.check_recent_temp_data(self.device_object.id)
        self.do_action_for_temper(temper_date)
        self.logger.info("already stop temper monitor thread")

    def check_recent_temp_data(self, device_pk):
        params = {
            "fields": "id,temperature,record_datetime",
            "record_datetime__gt": str(datetime.now() - timedelta(seconds=self.rest_time)),
            "record_datetime__lt": str(datetime.now()),
            "device__id": device_pk,
            "ordering": "-id"
        }
        return request(method="GET", url=device_temper_url, params=params)

    def do_action_for_temper(self, temper_date):
        for data in temper_date.get("devicetemperatures", ""):
            count = 0
            if float(data.get("temperature", "")) >= self.temp_alarm:
                count += 1
                if count >= 20:
                    stop_specific_device(self.device_object.device_label)
        return 1
