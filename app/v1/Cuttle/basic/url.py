from flask import Blueprint

from app.v1.Cuttle.basic.basic_views import TestOcrClass, TestIconClass

basic = Blueprint('basic', __name__)

basic.add_url_rule('/icon_test/', view_func=TestIconClass.as_view('icon_test'))
basic.add_url_rule('/ocr_test/', view_func=TestOcrClass.as_view('ocr_test'))




