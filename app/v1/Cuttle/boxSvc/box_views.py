from datetime import datetime

from flask import jsonify, request
from flask.views import MethodView

from app.libs.functools import execute_limit
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
        order_set_name = "set_on_order" if box_obj.init_status else "set_off_order"
        order_dict = getattr(box_setting, order_set_name)
        verified_list = box_obj.verfiy_box(order_dict)
        return jsonify({"verified_list": verified_list}), 200

    @staticmethod
    def temper_view(box_obj):
        order_dict = getattr(box_setting, "check_temperature_order")
        verified_list = box_obj.verfiy_box(order_dict)
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


class Port(MethodView):
    """
    开关单个port，iput：{"port:"PA-01","action":"on"}
    """

    def post(self):
        params_dict = request.get_json()
        try:
            response = on_or_off_singal_port(params_dict)
            if response:
                return jsonify(response), 200
            else:
                return jsonify({"status": "fail"}), 400
        except Exception as e:
            return jsonify({"status": f"connection with power box fail :{repr(e)}"}), 400


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
    return power_box_obj.judeg_result(order, response)


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
