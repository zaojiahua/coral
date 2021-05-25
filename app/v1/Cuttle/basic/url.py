from flask import Blueprint

basic = Blueprint('basic', __name__)

from app.v1.Cuttle.basic import basic_views
