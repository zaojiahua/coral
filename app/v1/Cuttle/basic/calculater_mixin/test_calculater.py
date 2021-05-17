import base64
import os
from collections import Counter
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.config.ip import OCR_IP
from app.config.setting import CORAL_TYPE
from app.config.url import coral_ocr_url
from app.execption.outer.error import APIException
from app.libs.http_client import request
from app.v1.Cuttle.basic.calculater_mixin.compare_calculater import FeatureCompareMixin, separate_point_pixel
from app.v1.Cuttle.basic.image_schema import IconTestSchema, OcrTestSchema
from app.v1.Cuttle.basic.setting import icon_threshold_camera, icon_threshold, icon_rate


class TestMixin(object):
    def test_icon_exist(self, exec_content, clear=True):
        data = IconTestSchema().load(exec_content)
        threshold = icon_threshold if CORAL_TYPE < 5 else icon_threshold_camera
        require_feature_number = int(threshold - (1 - data.get('threshold', 0.99)) * icon_rate)
        try:
            feature_point_length, _, _ = self.test_icon(data, clear)
        except APIException:
            return {"sample": 0, "required": require_feature_number, 'message': 'icon too week'}
        if len(feature_point_length) < require_feature_number:
            message = 'please lower the value of threshold'
        elif len(feature_point_length) < require_feature_number * 2:
            message = 'ok,but we suggest to change another icon'
        else:
            message = 'success'
        return {"sample": len(feature_point_length),
                "required": require_feature_number,
                'message': message}

    def test_icon(self, data, clear):
        feature_path = self._crop_image_and_save(data.get("input_image"), data.get("areas")[0], mark='icon')
        image_crop_path = self._crop_image_and_save(data.get("input_image"), data.get("crop_areas")[0])
        feature_point_length = self.shape_identify(cv2.imread(image_crop_path), cv2.imread(feature_path))
        if clear:
            self.remove_if_exist(data.get("input_image"), feature_path, image_crop_path)
        return feature_point_length, feature_path, image_crop_path

    def test_icon_position(self, exec_content):
        data = IconTestSchema().load(exec_content)
        try:
            response, icon_path, image_crop_path = self.test_icon(data, clear=False)
        except APIException as e:
            return {"error": e.description}
        if len(response) < 4:
            return {"error": 'sample point not enough'}
        code, centroids = FeatureCompareMixin.kmeans_clustering(response, 4)
        max_centro = Counter(code).most_common(2)[0][0]
        key_number_1 = Counter(code).most_common(2)[0][1]
        key_number_2 = Counter(code).most_common(2)[1][1]
        result = centroids[max_centro]
        result_x, result_y = separate_point_pixel(result)
        img = Image.open(image_crop_path).convert("RGB")
        img_draw = ImageDraw.Draw(img)
        length = max(np.array(img).shape[:2])
        length_cross = int(length * 0.03)
        img_draw.line(xy=(result_x - length_cross, result_y, result_x + length_cross, result_y), fill='green',
                      width=int(length * 0.007))
        img_draw.line(xy=(result_x, result_y - length_cross, result_x, result_y + length_cross), fill='green',
                      width=int(length * 0.007))
        output_buffer = BytesIO()
        output_icon_buffer = BytesIO()
        img.save(output_buffer, format='JPEG')
        Image.open(icon_path).convert("RGB").save(output_icon_buffer, format='JPEG')
        byte_data = output_buffer.getvalue()
        icon_byte_data = output_icon_buffer.getvalue()
        self.remove_if_exist(icon_path, data.get("input_image"), image_crop_path)
        return {
            "img_detected": 'data:image/jpeg;base64,' + base64.b64encode(byte_data).decode('utf8'),
            'icon': 'data:image/jpeg;base64,' + base64.b64encode(icon_byte_data).decode('utf8'),
            'key_point_one': key_number_1,
            'key_point_two': key_number_2,
        }

    def test_icon_position_fixed(self, exec_content):
        data = IconTestSchema().load(exec_content)
        icon_path = self._crop_image_and_save(data.get("input_image"), data.get("areas")[0], mark='icon')
        image_crop_path = self._crop_image_and_save(data.get("input_image"), data.get("crop_areas")[0])
        template = cv2.imread(icon_path)
        target = cv2.imread(image_crop_path)
        th, tw = template.shape[:2]
        result = cv2.matchTemplate(target, template, cv2.TM_SQDIFF_NORMED)
        cv2.normalize(result, result, 0, 1, cv2.NORM_MINMAX, -1)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        result_x = min_loc[0] + 1 / 2 * tw
        result_y = min_loc[1] + 1 / 2 * th
        img = Image.open(image_crop_path).convert("RGB")
        img_draw = ImageDraw.Draw(img)
        length = max(np.array(img).shape[:2])
        length_cross = int(length * 0.03)
        img_draw.line(xy=(result_x - length_cross, result_y, result_x + length_cross, result_y), fill='green',
                      width=int(length * 0.007))
        img_draw.line(xy=(result_x, result_y - length_cross, result_x, result_y + length_cross), fill='green',
                      width=int(length * 0.007))
        output_buffer = BytesIO()
        output_icon_buffer = BytesIO()
        img.save(output_buffer, format='JPEG')
        Image.open(icon_path).convert("RGB").save(output_icon_buffer, format='JPEG')
        byte_data = output_buffer.getvalue()
        icon_byte_data = output_icon_buffer.getvalue()
        self.remove_if_exist(icon_path, data.get("input_image"), image_crop_path)
        return {
            "img_detected": 'data:image/jpeg;base64,' + base64.b64encode(byte_data).decode('utf8'),
            'icon': 'data:image/jpeg;base64,' + base64.b64encode(icon_byte_data).decode('utf8'),
            'min_value': min_val
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
