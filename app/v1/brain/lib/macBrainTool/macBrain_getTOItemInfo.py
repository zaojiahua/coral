import json
import os

from app.v1.brain.lib import serviceData
from app.v1.brain.lib.macBrainTool import macBrian_reqJobLibSvc


class GetTOItemInfo:
    def __init__(self):
        self.TOItem_info = {}

    def init(self, TOItem):
        item_json_path = os.path.join(serviceData.brainLibPath, TOItem, "item.json")
        with open(item_json_path, "r", encoding="utf-8") as fh:
            self.TOItem_info = json.load(fh)
        return 0

    def get_TOItem_name(self):
        return self.TOItem_info["TOItemName"]

    def get_product(self):
        if "applyProducts" not in self.TOItem_info.keys():
            return 0
        else:
            return self.TOItem_info["applyProducts"]

    def get_img_match(self):
        img_match_info = {}
        if "targetImgMatchFuncAParams" in self.TOItem_info:
            img_match_info = self.TOItem_info["targetImgMatchFuncAParams"]
        return img_match_info

    def get_text_match(self):
        text_match_info = {}
        if "targetTextMatchFuncAParams" in self.TOItem_info:
            text_match_info = self.TOItem_info["targetTextMatchFuncAParams"]
        return text_match_info

    @staticmethod
    def get_op_exce_block(self):
        eblk_dict = {}
        return eblk_dict

    def get_op_exec_module(self):
        return self.TOItem_info["operationPackage"]["opModule"]

    def get_op_job_id(self):
        return self.TOItem_info["operationPackage"]["jobId"]

    def get_op_job_path(self):
        job_id = self.get_op_job_id()
        job_path = macBrian_reqJobLibSvc.reqJobLibSvc(job_id)
        return job_path
