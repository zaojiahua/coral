import logging
import threading

from flask import request

from app.config.log import TBOARD_LOG_NAME
from app.execption.outer.error_code.tboard import CreateTboardError
from app.v1.tboard.validators.tboardSchema import TboardSchema, TboardJobPrioritySchema
from app.v1.tboard.views import tborad_router
from app.libs.log import setup_logger

"""
{
    "device_label_list": [
      "dior---msm8226---c1a65aa6",
      "dior---msm8226---c1a65aa7"
    ],required
    "job_label_list": [
      "job-534aac2d-6d55-4b9e-b70b-9d43e7626cd1",
      "job-a03de750-6739-4e35-8a31-5a60ca01cf8a"
    ],required
    "repeat_time": Integer,
    "owner_label": Str,required
    board_name:Str 
}
"""


@tborad_router.route('/insert_tboard/', methods=['POST'])
def insert_tboard():
    logger = setup_logger(TBOARD_LOG_NAME, f'{TBOARD_LOG_NAME}.log')
    logger.info(f"【Tboard】 receive a tboard from post request {request.json}")
    return insert_tboard_inner(**request.json)


def insert_tboard_inner(**kwargs):
    # 调用 make_user 返回 TBoardViewModel对象

    res = TboardJobPrioritySchema().load_or_parameter_exception(kwargs) if kwargs.get(
        "device_mapping") else TboardSchema().load_or_parameter_exception(kwargs)
    tboard_obj = res.create_tboard()
    if tboard_obj == -1:
        raise CreateTboardError(description='not useful device')
    # 异步向下执行
    t1 = threading.Thread(target=tboard_obj.start_tboard, args=(res.jobs,))
    t1.start()
    return {
               "state": "OK",
               "id": tboard_obj.tboard_id,
               "board_name": tboard_obj.board_name
           }, 200
