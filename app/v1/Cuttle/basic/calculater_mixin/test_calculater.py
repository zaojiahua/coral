import os

from app.config.ip import OCR_IP
from app.config.url import coral_ocr_url
from app.libs.http_client import request
from app.v1.Cuttle.basic.image_schema import IconTestSchema, OcrTestSchema
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_threshold, icon_rate


class TestMixin(object):
    def test_icon_exist(self,exec_content):
        data = IconTestSchema().load(exec_content)
        feature_refer = self._crop_image(data.get("input_image"), data.get("areas")[0])
        image_crop = self._crop_image(data.get("input_image"), data.get("crop_areas")[0])
        feature_point_length = len(self.shape_identify(image_crop, feature_refer))
        os.remove(data.get("input_image"))
        return {"sample": feature_point_length, "required": int(icon_threshold - (1 - data.get('threshold', 0.99)) * icon_rate)}

    def test_icon_position(self,exec_content):
        pass



    def test_ocr_result(self,exec_content):
        data = OcrTestSchema().load(exec_content)
        print(data)
        pic_path = self._crop_image_and_save(data.get("input_image"), data.get("areas")[0]) if data.get("areas") else data.get("input_image")
        if data.get("ocr_choice") == "2":
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               ip=f"http://{OCR_IP}:8090")
        else:
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               ip=f"http://{OCR_IP}:8089")
        print(response)
        return response

