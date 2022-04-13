from flask import Blueprint

from app.v1.Cuttle.macPane.pane_view import PaneOriginalView, PaneAssisDeleteView, FilePushView, PerformancePictureView, \
    AutoPaneBorderView, update_phone_model, PaneClickTestView, PaneCoordinateView, PaneMergePicView, \
    PaneLocateDeviceView
from app.v1.Cuttle.macPane.pane_view import PaneUpdateView, PaneDeleteView, PaneFunctionView, \
    PaneBorderView

pane = Blueprint('pane', __name__)
# 更新设备相关信息，可见于给设备配置继电器接口/温感片等操作
pane.add_url_rule('/device_update/', view_func=PaneUpdateView.as_view('pane_create_view'))
# 在机型管理页面更改机型属性时，用来同步更改coral内的设备缓存信息
pane.add_url_rule('/phone_module_update/', view_func=update_phone_model, methods=['POST'])
# 主机注销
pane.add_url_rule('/device_leave/', view_func=PaneDeleteView.as_view('pane_leave_view'))
# 僚机注销
pane.add_url_rule('/device_assis_leave/', view_func=PaneAssisDeleteView.as_view('pane_assis_leave_view'))
# 获取一张手机照片/1234型柜获取手机adb截图，5型柜获取带roi且旋转后的摄像头照片
pane.add_url_rule('/snap_shot/', view_func=PaneFunctionView.as_view('snap_shot_view'))
# 获取摄像头下的一张原始照片，会清空之前的roi设置，重新开启一个cam(用在5型柜配置机柜信息第一步)
pane.add_url_rule('/original_picture/', view_func=PaneOriginalView.as_view('original_picture_view'))
pane.add_url_rule('/coordinate_click_test/', view_func=PaneClickTestView.as_view('click_test_view'))

# 获取性能测试图片,性能测试查看结果页面调用, （常见用户连接错误wifi导致获取不到图片显现）
pane.add_url_rule('/performance_picture/', view_func=PerformancePictureView.as_view('performance_picture'))
# 框选手机屏幕边框后，会收到前端的设置border的请求(用在5型柜配置机柜信息第2步)
pane.add_url_rule('/device_border/', view_func=PaneBorderView.as_view('device_border'))
# 自动获取边框的接口，用在5型柜配置机柜页面自动获取按钮
pane.add_url_rule('/get_roi/', view_func=AutoPaneBorderView.as_view('get_roi'))
# 给所有adb连接状态的手机推图片的接口，仅在天津给编辑用例人使用
pane.add_url_rule('/file_push/', view_func=FilePushView.as_view('file_push'))
# 建立坐标系统
pane.add_url_rule('/coordinate/', view_func=PaneCoordinateView.as_view('coordinate'))
# 重置拼图矩阵
pane.add_url_rule('/reset_h/', view_func=PaneMergePicView.as_view('reset_h'))
# 调试被测试设备的距离
pane.add_url_rule('/locate_device/', view_func=PaneLocateDeviceView.as_view('locate_device'))
