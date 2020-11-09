import logging

from flask import Blueprint

from app.config.setting import TBOARD_LOG_NAME

tborad_router = Blueprint('tborad', __name__)

logger = logging.getLogger(TBOARD_LOG_NAME)

# # https://www.cnblogs.com/51kata/p/5288392.html
# @tborad_router.before_request
# def print__():
#     if request.method == "GET":
#         logger.info(f"GET args:{request.args.to_dict()}")
#     elif request.method == "POST":
#         logger.info(f"GET args:{request.json}")


from app.v1.tboard.views import (
    insert_tboard,
    get_dut_progress,
    remove_tboard,
    stop_specific_device
)
