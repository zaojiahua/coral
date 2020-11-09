from flask import Blueprint

from app.v1.Cuttle.boxSvc.box_views import Port, BoxManagement

resource = Blueprint('resource', __name__)
# add
add_request_sample = {
    "name": "PA",
    "ip": "10.80.3.121",
    "port": 20000,
    "init_status": True,
    "total_number": 8,
    "method": "socket",
    "type": "power"
}
# action
action_request_sample = {"port": "PA-01", "action": True}

resource.add_url_rule('/action', view_func=Port.as_view("power_action"))
resource.add_url_rule('/box', view_func=BoxManagement.as_view("change_power_box"))
resource.add_url_rule('/box/<string:name>', view_func=BoxManagement.as_view("remove_power"))
