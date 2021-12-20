import os

from flask import request, Blueprint, jsonify
from flask.views import MethodView

from app.config.setting import LOG_DIR
from app.libs.logresponse import log_response

log = Blueprint('log', __name__)

# 这个是cedar admin页面进去才能看到的系统日志页面，现在基本上没在用，但页面上目前还能正常访问。
class LogView(MethodView):
    def get(self):
        param_dict = request.args
        try:
            limit = int(param_dict.get("limit"))
            offset = int(param_dict.get("offset"))
        except:
            return "parameter should include limit(Int) and offset(Int)", 400
        file_name_list = sorted(os.listdir(os.path.join(LOG_DIR, "log")))
        header = {"Total-Count": file_name_list.__len__()}
        if offset >= file_name_list.__len__():
            return "offset should smaller than total count", 400, header
        if offset + limit >= file_name_list.__len__():
            return jsonify(file_name_list[offset:]), 200, header
        else:
            return jsonify(file_name_list[offset:offset + limit]), 200, header


class LogContentView(MethodView):
    def get(self, file_name):
        param_dict = request.args
        file_name = os.path.join(LOG_DIR, "log", file_name)
        return log_response(param_dict, file_name)


log.add_url_rule('/list/', view_func=LogView.as_view('log_list'))
log.add_url_rule('/content/<string:file_name>/', view_func=LogContentView.as_view('log_content'))
