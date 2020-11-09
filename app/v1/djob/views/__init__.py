import logging

from flask import Blueprint

from app.config.setting import DJOB_LOG_NAME

djob_router = Blueprint('djob', __name__)

logger = logging.getLogger(DJOB_LOG_NAME)
# 导入模块，在flask启动时，会调用执行写入到rule map中:注册router
from app.v1.djob.views import (
    insert_djob,
    remove_djob,
    rds_detail
)
