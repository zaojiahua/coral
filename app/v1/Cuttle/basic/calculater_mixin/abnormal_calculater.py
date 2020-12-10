from app.v1.Cuttle.basic.operator.handler import Abnormal


class AbnormalMixin(object):
    # 主要负责写共用的abnormal
    process_list = [
        # mark 为str 因为adb func 返回str
        Abnormal(mark="restarting adbd as root", method="reconnect", code=-6),
        Abnormal("device offline", "reconnect", -5),
        Abnormal("not found", "reconnect", -3),
        Abnormal("protocol fault", "reconnect", -2),
        Abnormal("daemon not running", "reconnect", -1),
        Abnormal("unable to connect", "reconnect", -7),
    ]
    skip_list = []

    def ignore(self,*args):
        pass
