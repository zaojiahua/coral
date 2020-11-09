import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.libs.log import setup_logger
from app.v1.Cuttle.boxSvc import box_setting
from app.v1.Cuttle.boxSvc.box_models import Box
from app.v1.Cuttle.boxSvc.request_sender import check_from_reef, send_available_port_to_reef


def deal_with_singal_box(box):
    # 验证单个木盒
    box_obj = Box(pk=box.get("name"))
    box_obj.update_attr(**box)
    if box_obj.type == "power":
        order_set_name = "set_on_order" if box_obj.init_status else "set_off_order"
    else:
        order_set_name = "check_temperature_order"
    order_dict = getattr(box_setting, order_set_name)
    verfied_list = box_obj.verfiy_box(order_dict)
    return verfied_list


def box_init():
    # todo finished it when reef already have corresponding api
    # 1 从reef download 所有木盒信息
    # 2 填入redis
    # 3 遍历port 发送开指令
    # 4 收集返回正确的port
    logger = setup_logger("box_init", r'box_init.log')
    box_list = check_from_reef()
    box_list = deal_with_reef_data(box_list, logger)
    for box in box_list:
        box_obj = Box(pk=box.get("name"))
        box_obj.update_attr(**box)
    # 并发验证多个木盒
    future_list = [ThreadPoolExecutor().submit(deal_with_singal_box, box) for box in box_list]
    total_verified_list = [future.result() for future in as_completed(future_list) if future.exception() is None]
    logger.info(f"power restart ,total_verfied_list:{total_verified_list} ")
    # response = send_available_port_to_reef(total_verfied_list)


def deal_with_reef_data(box_list, logger):
    try:
        for box in box_list:
            if isinstance(box.get("config"), str):
                box["config"] = json.loads(box.get("config"))
            box["init_status"] = box.get("config").get("init_status")
            box["port"] = box.get("config").get("port")
            box["total_number"] = box.get("config").get("total_number")
            box["method"] = box.get("config").get("method")
        return box_list
    except Exception as e:
        logger.error(f"transform reef's data fail exception:{repr(e)}")
