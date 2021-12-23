from flask import Blueprint

from app.v1.Cuttle.boxSvc.box_views import SetPort, BoxManagement, CheckPort

resource = Blueprint('resource', __name__)
# add
add_request_sample = {
    "name": "PA",
    "ip": "10.80.3.121",
    "port": 20000,
    "init_status": True,
    "total_number": 8,
    "method": "socket",  # 目前存货都是socket模式的，开发时也有http模式的
    "type": "power"
}
# action
action_request_sample = {"port": "PA-01", "action": "on"}
# 对盒子内单一路的控制
resource.add_url_rule('/power_action', view_func=SetPort.as_view("power_action"))
# 添加或删除一个铁盒（继电器/温感盒子）盒子有自己的ip，port，默认开关模式等参数详见上面add_request_sample变量。
# 每次添加后都会自动遍历验证盒子内所有路（一般16路）端口正常工作，并返回可用的端口名称list
resource.add_url_rule('/box', view_func=BoxManagement.as_view("change_power_box"))
resource.add_url_rule('/box/<string:name>', view_func=BoxManagement.as_view("remove_power"))
resource.add_url_rule('/check_power', view_func=CheckPort.as_view("check_port_status"))
