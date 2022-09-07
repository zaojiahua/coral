import logging
from datetime import datetime

from flask import jsonify, request
from flask.views import MethodView

from app.libs.func_tools import execute_limit
from app.execption.outer.error_code.box import ConnectPowerFail
from app.v1.Cuttle.basic.setting import set_global_value, get_global_value
from app.v1.Cuttle.boxSvc import box_setting
from app.v1.Cuttle.boxSvc.box_models import Box
from app.v1.Cuttle.boxSvc.request_sender import send_order, send_temper_to_reef


class BoxManagement(MethodView):
    def post(self):
        try:
            # 1 save json to redis
            config = request.get_json()
            box_obj = Box(pk=config.get("name"))
            box_obj.update_attr(**config)
            # 2 verify
            if config.get("type") == "power":
                return self.power_view(box_obj)
            elif config.get("type") == "temp":
                return self.temper_view(box_obj)
            else:
                return jsonify({"fail": "can not find usable type"}), 400
        except Exception as e:
            return jsonify({"reason": repr(e), "status": "can not connect box"}), 400

    @staticmethod
    def power_view(box_obj):
        # order_set_name = "set_on_order" if box_obj.init_status else "set_off_order"
        order_set_name = "set_off_order" if box_obj.init_status else "set_on_order"
        order_dict = getattr(box_setting, order_set_name)
        verified_list = box_obj.verify_box(order_dict)
        return jsonify({"verified_list": verified_list}), 200

    @staticmethod
    def temper_view(box_obj):
        order_dict = getattr(box_setting, "check_temperature_order")
        verified_list = box_obj.verify_box(order_dict)
        return jsonify({"verified_list": verified_list}), 200

    def delete(self, name):
        # remove data in redis
        power_box_obj = Box(pk=name)
        power_box_obj.remove()
        return "ok", 204
        # use this part code when feature-deviceModel branch finished
        # def update_device_attr(self,port_list):
        #     search_str = "astra::{}::fld::*::power_port".format(Device.__name__.lower())
        #     for i in port_list:
        #         for j in redis_client.keys(search_str):
        #             if i == redis_client.get(j):
        #                 device_label = j.split("::")[:-2]
        #                 Device(pk= device_label).power_port = None


class SetPort(MethodView):
    """
    开关单个port，input：{"port:"PA-01","action":"on"}
    """

    def post(self):

        params_dict = request.get_json()
        power_name = params_dict["port"].split("-")
        power_name.pop()
        power_box_obj = Box(pk="-".join(power_name))
        if not power_box_obj.ip:
            return jsonify({"status": "fail"}), 400
        power_total_nums = power_box_obj.total_number
        try:
            if power_total_nums == 16 or power_total_nums == 8:
                params_dict['action'] = True if params_dict['action'] == 'on' else False
            else:
                params_dict['action'] = True if params_dict['action'] == 'off' else False
            response = on_or_off_singal_port(params_dict)
            if response:
                return jsonify(response), 200
            else:
                return jsonify({"status": "fail"}), 400
        except ConnectPowerFail:
            raise ConnectPowerFail


class CheckPort(MethodView):
    """
    检查单个继电器状态
    """

    def post(self):
        """
        只支持8路继电器和16路继电器查询
        """
        port = request.get_json()['port']
        try:
            port_list = port.split("-")
            port_list.pop()
            power_box_obj = Box(pk="-".join(port_list))
            if not power_box_obj.ip:
                return False
            power_total_nums = power_box_obj.total_number
            check_status_order = box_setting.check_power_order[power_total_nums]
            response = send_order(power_box_obj.ip, power_box_obj.port, check_status_order, power_box_obj.method)
            port_status = parse_rev_data(port, response, power_box_obj.init_status, power_total_nums)
            if port_status:
                return jsonify({"status": "on"}), 200
            else:
                return jsonify({"status": "off"}), 200
        except ConnectPowerFail:
            raise ConnectPowerFail


class PortChargeSlg(MethodView):
    def post(self):
        # 更新充电口的充电策略
        port_slg_info = request.get_json()
        save_charge_slg(port_slg_info)
        return jsonify({"result": "0"}), 200


def on_or_off_singal_port(params_dict):
    # 开/关单个port
    port = params_dict.get("port")
    port_list = port.split("-")
    port_list.pop()
    power_box_obj = Box(pk="-".join(port_list))
    if not power_box_obj.ip:
        return False
    on_off = not (params_dict.get("action") ^ power_box_obj.init_status)
    order_set_name = "set_off_order" if on_off == False else "set_on_order"
    power_box_obj.logger.info(
        f"port:{port}--1.actiton:{params_dict.get('action')} 2.status:{power_box_obj.init_status}  3.order_set_name:{order_set_name}")
    order_dict = getattr(box_setting, order_set_name)
    order = order_dict.get(port.split("-")[-1])
    response = send_order(power_box_obj.ip, power_box_obj.port, order, power_box_obj.method)
    power_box_obj.logger.info(f"on_or_off_singal_port result：{response}")
    return power_box_obj.judge_result(order, response)


@execute_limit(5)
def get_port_temperature(port_list):
    data_list = []
    for port in port_list:
        port_list = port.split("-")
        port_list.pop()
        box_obj = Box(pk="-".join(port_list))
        order_dict = getattr(box_setting, "check_temperature_order")
        order = order_dict.get(port.split("-")[-1])
        response = send_order(box_obj.ip, box_obj.port, order, box_obj.method)
        if len(response) != 14 or not 0 < int(response[6:10], 16) * 0.01 < 100:
            break
        temperature = round(int(response[6:10], 16) * 0.01, 2)
        # from app.libs.http_client import request
        # temp_ort_msg = request(url=machTempPortUrl.format(port), params={"fields": "id"})
        data = {}
        data["description"] = "no description"
        data["temp_port"] = port
        data["record_datetime"] = str(datetime.now())
        data["temperature"] = temperature
        data_list.append(data)
        box_obj.logger.debug(f"check one times temperature:{temperature} at port :{port}")
    result = send_temper_to_reef(data_list)
    return 0


def hexToBinary(hexNumber):
    # 1. hex to dec
    decNumber = int(str(hexNumber), 16)
    # 2. dec to bin
    binNumber = bin(decNumber)
    n = binNumber[2:]
    s = n.zfill(8)
    return s


def parse_rev_data(port, rev_data, init_status, num):
    """
    :param port: 继电器充电口编号
    :param rev_data: 发送检查充电口状态指令后收到的回复数据  eg: fe01017ee1bc
    :param init_status: 继电器通电后的初始状态
    :param num: 继电器的充电口数量，目前只支持8路和16路
    :return: True -- ON, False -- OFF
    """
    if num == 8:
        s = hexToBinary(rev_data[6:8])
        portState = int(s[num - int(port[-2:])])
        if init_status:
            status = True if portState == 1 else False
        else:
            status = False if portState == 1 else True
        return status
    else:
        s8 = hexToBinary(rev_data[6:8])
        s_8 = hexToBinary(rev_data[8:10])
        s = (str(s_8) + str(s8))[::-1]
        num = int(port[-2:])
        portState = int(s[num - 1])
        status = not (bool(portState) ^ init_status)
        return status


def save_charge_slg(data_from_reef, port_nums=1):
    print("*"*10)
    print(data_from_reef)
    """
    input: {"powerports": [{"port": "PA-15","powerstrategy": [
                {"id": 1,"min_value": 30,"max_value": 60,"start_time": "18:30:59","end_time": "18:31:04","is_default": true}
            ]
        },
        {
            "port": "PA-11",
            "powerstrategy": []
        }]
    output: {
        "PA-01":{"default_slg":{"start":30, "end":80},
                 "set_by_user_slg":[{"start"：20, "end":50, "timer":["00:00:00", "12:00:00"]},
                                    {"start"：30, "end":80, "timer":["14:00:00", "16:00:00"]]
                 },
        "PA-02":{}
    }
    """
    ports_info = data_from_reef["powerports"]
    ports_info_size = len(ports_info)
    # 判断是否取到了期望数量的端口充电策略
    if ports_info_size < port_nums:
        raise Exception

    powers_slgs = get_global_value("port_charge_strategy")
    for i in range(0, ports_info_size):
        port_name = ports_info[i]["port"]
        default_slg, set_by_user = {}, []
        for strategy in ports_info[i]["powerstrategy"]:
            if strategy["is_default"]:
                default_slg = {"min_value": strategy['min_value'], "max_value": strategy['max_value']}
            else:
                target = {"min_value": strategy["min_value"], "max_value": strategy["max_value"],
                          "timer": [strategy["start_time"][:-3], strategy["end_time"][:-3]]}
                set_by_user.append(target)
        port_name_slg = {"default_slg": default_slg, "set_by_user_slg": set_by_user}
        if port_name in powers_slgs.keys():
            powers_slgs[port_name] = port_name_slg
        else:
            powers_slgs.update({port_name: port_name_slg})
    print(f"port_charge_strategy: {powers_slgs}")
    set_global_value("port_charge_strategy", powers_slgs)
    return 0
