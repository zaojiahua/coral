import logging

from flask import Blueprint

from app.config.setting import TBOARD_LOG_NAME


tborad_router = Blueprint('tborad', __name__)
logger = logging.getLogger(TBOARD_LOG_NAME)


from app.v1.tboard.views import (
    insert_tboard,
    get_dut_progress,
    remove_tboard,
    stop_specific_device
)
