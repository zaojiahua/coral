from flask import Blueprint

from app.v1.Cuttle.basic.basic_views import TestOcrClass, TestIconClass, TestIconPositionClass

basic = Blueprint('basic', __name__)

basic.add_url_rule('/icon_test/', view_func=TestIconClass.as_view('icon_test'))
basic.add_url_rule('/icon_test_position/', view_func=TestIconPositionClass.as_view('icon_test_position'))
basic.add_url_rule('/ocr_test/', view_func=TestOcrClass.as_view('ocr_test'))




