from flask import Blueprint

from app.v1.Cuttle.basic.basic_views import TestClass

basic = Blueprint('basic', __name__)

basic.add_url_rule('/icon_test/', view_func=TestClass.as_view('icon_test'))




