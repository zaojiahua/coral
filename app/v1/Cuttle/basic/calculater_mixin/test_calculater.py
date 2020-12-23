import os

from app.v1.Cuttle.basic.image_schema import IconTestSchema
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
