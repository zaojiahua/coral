from flask import Blueprint

basic = Blueprint('basic', __name__)

from .basic_views import test_icon_exist, test_position, test_position_fixed, ocr_test
