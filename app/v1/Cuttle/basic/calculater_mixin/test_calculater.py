import base64
import os
from io import BytesIO

import cv2
import numpy as np

from app.config.ip import OCR_IP
from app.config.setting import CORAL_TYPE
from app.config.url import coral_ocr_url
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.compare_calculater import FeatureCompareMixin, separate_point_pixel
from app.v1.Cuttle.basic.image_schema import IconTestSchema, OcrTestSchema
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_threshold, icon_rate
from collections import Counter
from PIL import Image, ImageDraw, ImageFont


class TestMixin(object):
    def test_icon_exist(self, exec_content, clear=True):
        data = IconTestSchema().load(exec_content)
        feature_point_length, _, _ = self.test_icon(data, clear)
        threshold = icon_threshold if CORAL_TYPE < 5 else icon_threshold_camera
        require_feature_number = int(threshold - (1 - data.get('threshold', 0.99)) * icon_rate)
        message = 'please lower the value of threshold' if len(
            feature_point_length) < require_feature_number else 'success'
        return {"sample": len(feature_point_length),
                "required": require_feature_number,
                'message': message}

    def test_icon(self, data, clear):
        feature_path = self._crop_image_and_save(data.get("input_image"), data.get("areas")[0], mark='icon')
        image_crop_path = self._crop_image_and_save(data.get("input_image"), data.get("crop_areas")[0])
        feature_point_length = self.shape_identify(cv2.imread(image_crop_path), cv2.imread(feature_path))
        if clear:
            self.remove_if_exist(data.get("input_image"),feature_path,image_crop_path)
        return feature_point_length, feature_path, image_crop_path

    def test_icon_position(self, exec_content):
        data = IconTestSchema().load(exec_content)
        response, icon_path, image_crop_path = self.test_icon(data, clear=False)
        if len(response) < 4:
            return {"error": 'sample point not enough'}
        code, centroids = FeatureCompareMixin.kmeans_clustering(response, 4)  # five centroids
        max_centro = Counter(code).most_common(1)[0][0]
        result = centroids[max_centro]
        result_x, result_y = separate_point_pixel(result)
        img = Image.open(image_crop_path).convert("RGB")
        img_draw = ImageDraw.Draw(img)
        length = max(np.array(img).shape[:2])
        length_cross = int(length * 0.03)
        img_draw.line(xy=(result_x - length_cross, result_y, result_x + length_cross, result_y), fill='green',
                      width=int(length * 0.005))
        img_draw.line(xy=(result_x, result_y - length_cross, result_x, result_y + length_cross), fill='green',
                      width=int(length * 0.005))
        output_buffer = BytesIO()
        output_icon_buffer = BytesIO()
        img.save(output_buffer, format='JPEG')
        Image.open(icon_path).convert("RGB").save(output_icon_buffer, format='JPEG')
        byte_data = output_buffer.getvalue()
        icon_byte_data = output_icon_buffer.getvalue()
        self.remove_if_exist(icon_path,data.get("input_image"),image_crop_path)
        return {
            "img_detected": 'data:image/jpeg;base64,' + base64.b64encode(byte_data).decode('utf8'),
            'icon': 'data:image/jpeg;base64,' + base64.b64encode(icon_byte_data).decode('utf8')
        }

    def test_ocr_result(self, exec_content):
        data = OcrTestSchema().load(exec_content)
        pic_path = self._crop_image_and_save(data.get("input_image"), data.get("areas")[0]) if data.get(
            "areas") else data.get("input_image")
        if data.get("ocr_choice") == "2":
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               ip=f"http://{OCR_IP}:8090")
        else:
            response = request(method="POST", url=coral_ocr_url, files={"image_body": open(pic_path, "rb")},
                               ip=f"http://{OCR_IP}:8089")
        self.remove_if_exist(pic_path, data.get("input_image"))
        return response

    def remove_if_exist(self, *args):
        for i in args:
            if os.path.exists(i):
                os.remove(i)
