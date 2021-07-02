from flask import Blueprint

from app.v1.Cuttle.macPane.pane_view import PaneOriginalView, PaneAssisDeleteView, FilePushView, PerformancePictureView, \
    AutoPaneBorderView, update_phone_model
from app.v1.Cuttle.macPane.pane_view import PaneUpdateView, PaneDeleteView, PaneFunctionView, PaneConfigView, \
    PaneBorderView

pane = Blueprint('pane', __name__)

data_example = {
    "auto_test": True,
    "device_label": "cactus---mt6765---65a4066f7d29",
    "powerport": {
        "port": "PA-01"
    },

    "monitor_index": "999",
    "device_name": "xuegao",
    "tempport": [
        {
            "port": "TA-01"
        }
    ]
}

leave_data_example = {
    "ip_address": "10.80.3.117",
    "device_label": "cactus---mt6765---65a4066f7d29",
    "tempport": [
        {
            "port": "TA-01"
        }
    ]
}
pane.add_url_rule('/device_update/', view_func=PaneUpdateView.as_view('pane_create_view'))
pane.add_url_rule('/phone_module_update/', view_func=update_phone_model,methods=['POST'])

pane.add_url_rule('/device_leave/', view_func=PaneDeleteView.as_view('pane_leave_view'))
pane.add_url_rule('/device_assis_leave/', view_func=PaneAssisDeleteView.as_view('pane_assis_leave_view'))
# 获取一张手机照片/1234型柜获取手机adb截图，5型柜获取带roi且旋转后的摄像头照片
pane.add_url_rule('/snap_shot/', view_func=PaneFunctionView.as_view('snap_shot_view'))
# 获取摄像头下的一张原始照片，会清空之前的roi设置，重新开启一个cam
pane.add_url_rule('/original_picture/', view_func=PaneOriginalView.as_view('original_picture_view'))

# 获取性能测试图片
pane.add_url_rule('/performance_picture/', view_func=PerformancePictureView.as_view('performance_picture'))
# pane.add_url_rule('/device_arm_camera/', view_func=PaneConfigView.as_view('device_in_slot'))
# 框选手机屏幕边框后，会收到前端的设置border的请求
pane.add_url_rule('/device_border/', view_func=PaneBorderView.as_view('device_border'))
# 自动获取边框的接口
pane.add_url_rule('/get_roi/', view_func=AutoPaneBorderView.as_view('get_roi'))
# 给所有adb连接状态的手机推图片的接口，仅在天津给编辑用例人使用
pane.add_url_rule('/file_push/', view_func=FilePushView.as_view('file_push'))

