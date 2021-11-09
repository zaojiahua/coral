import json
import os

import cv2
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE


def verify_exist(path):
    if not os.path.exists(path):
        raise ValidationError('path not exist')


def verify_format(str):
    coor_list = str.strip().split(" ")
    if len(coor_list) != 2:
        raise ValidationError('params wrong format --only one blank')
    try:
        for coor in coor_list:
            if float(coor) > 5000:
                raise ValidationError('need isdigit(<5000) parameters ')
    except ValueError:
        raise ValidationError('color coordinate should be digit')


def verify_not_relative_coor(str):
    coor_list = str.strip().split(" ")
    try:
        for coor in coor_list:
            if float(coor) < 1:
                raise ValidationError('color coordinate should be absolutely')
    except ValueError:
        raise ValidationError('color coordinate should be digit')


def verify_image(image_path):
    im = cv2.imread(image_path)
    if im is None:
        raise ValidationError('image not correct format')
    s = im.shape[0] * im.shape[1]
    if s < 100:
        raise ValidationError('image need bigger size ')


def verify_has_grep(cmd):
    if not "grep" in cmd and not "findstr" in cmd:
        raise ValidationError('input adb order should have "grep"/"findstr" ')


def load_config_file_v1(data):
    path = data.get("config")
    try:
        with open(path, "r") as json_file:
            json_data = json.load(json_file)
            areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                     "area" + str(i) in json_data.keys()]
            threshold = float(json_data.get("threshold", 0.99))
        data["areas"] = areas if areas != [] else [[0, 0, 1, 1]]
        data["threshold"] = threshold
        return data
    except (FileNotFoundError, TypeError):
        data["areas"] = [[0, 0, 1, 1]]
        data["threshold"] = 0.99
        return data


class ImageOriginalSchema(Schema):
    config = fields.String(required=True, data_key="configFile", validate=verify_exist)

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        path = data.get("config")
        with open(path, "r") as json_file:
            json_data = json.load(json_file)
            areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                     "area" + str(i) in json_data.keys()]
            threshold = float(json_data.get("threshold", 0.99))
        data["areas"] = areas if areas != [] else [[1, 1, 1, 1]]
        data["threshold"] = threshold
        return data


class ImageBasicSchema(ImageOriginalSchema):
    input_im = fields.String(required=False, data_key="inputImgFile")
    output_path = fields.String(data_key="outputPath")


class ImageBasicSchemaCompatible(ImageBasicSchema):
    config = fields.String(data_key="configFile")

    @post_load()
    def explain(self, data, **kwargs):
        optional_input_image = data.get('optional_input_image')
        try:
            exist_input_im = os.path.split(data['input_im'])[1]
        except Exception:
            exist_input_im = False

        data['exist_input_im'] = exist_input_im
        if not optional_input_image or (optional_input_image and exist_input_im):
            input_img_file = data.get('input_im')
            if not input_img_file:
                raise ValidationError('path not exist')
            else:
                verify_exist(input_img_file)
                verify_image(input_img_file)
        else:
            data['input_im'] = None
        return load_config_file_v1(data)


class ImageOnlyConfigCompatible(ImageOriginalSchema):
    # 向前兼容已有用例中，ConfigFile实际指明configArea的情况。允许configfile非必填。解决历史遗留但已经不允许更改的问题
    # 不能使用于图标识别的方法中
    config = fields.String(data_key="configFile")

    @post_load()
    def explain(self, data, **kwargs):
        return load_config_file_v1(data)


class ImageSchemaCompatible(ImageBasicSchemaCompatible):
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(verify_exist, verify_image))


class ImageSchema(ImageBasicSchema):
    # configArea可以为空，configFile不能为空
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(verify_exist, verify_image))


class ImageRealtimeSchema(ImageBasicSchemaCompatible):
    input_im_2 = fields.String(required=True, data_key="inputImgFile2", validate=(verify_exist, verify_image))


class ImageColorSchema(ImageBasicSchemaCompatible):
    color = fields.String(required=True, data_key="color")


class ImageColorPostionSchema(ImageBasicSchemaCompatible):
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(verify_exist, verify_image))
    position = fields.String(required=True, data_key="position", validate=verify_format)


class ImageMainColorSchema(ImageColorSchema):
    percent = fields.String(required=True, data_key="percent")


class ImageColorRelativePositionBaseSchema(Schema):
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(verify_exist, verify_image))
    config = fields.String(required=True, data_key="configFile")
    input_im = fields.String(required=True, data_key="inputImgFile", validate=(verify_exist, verify_image))
    output_path = fields.String(data_key="outputPath")

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        return load_config_file_v1(data)


class ImageColorRelativePositionSchema(ImageColorRelativePositionBaseSchema):
    requiredWords = fields.String(required=True, data_key="requiredWords")
    xyShift = fields.String(required=True, data_key="xyShift", validate=verify_format)
    position = fields.String(required=True, data_key="position", validate=verify_format)


class ImageAreaSchema(ImageSchema):
    area_config = fields.String(required=False, data_key="configArea")

    @post_load()
    def explain(self, data, **kwargs):
        crop_area_path = data.get("area_config")
        data = super().explain(data, **kwargs)
        try:
            with open(crop_area_path, "r") as json_file:
                json_data = json.load(json_file)
                areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                         "area" + str(i) in json_data.keys()]
            data["crop_areas"] = areas if areas != [] else [[0, 0, 1, 1]]
            return data
        except (FileNotFoundError,TypeError):
            data["crop_areas"] = [[0, 0, 1, 1]]
            return data


class ImageAreaWithoutInputSchema(ImageAreaSchema):
    input_im = fields.String(required=False, data_key="inputImgFile")


class VideoBaseSchema(Schema):
    video_file = fields.String(required=True, data_key="videoFile")
    start_config = fields.String(required=True, data_key="startConfig", validate=verify_exist)
    end_config = fields.String(required=True, data_key="endConfig", validate=verify_exist)

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        start_config_path = data.get("start_config")
        end_config_path = data.get("end_config")
        data = self._get_data(data, start_config_path, "start")
        return self._get_data(data, end_config_path, "end")

    def _get_data(self, data, path, prex):
        with open(path, "r") as json_file:
            json_data = json.load(json_file)
            areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                     "area" + str(i) in json_data.keys()]
            threshold = float(json_data.get("threshold", 0.99))
        data[f"{prex}_areas"] = areas if areas != [] else [[1, 1, 1, 1]]
        data[f"{prex}_threshold"] = threshold
        return data


class VideoWordsSchema(VideoBaseSchema):
    start_words = fields.String(required=True, data_key="startWords")
    end_words = fields.String(required=True, data_key="endWords")


class VideoPicSchema(VideoBaseSchema):
    end_image = fields.String(required=True, data_key="endImage", validate=(verify_exist, verify_image))
    start_image = fields.String(required=True, data_key="startImage", validate=(verify_exist, verify_image))
    start_icon_config = fields.String(required=True, data_key="startIconConfig", validate=verify_exist)
    end_icon_config = fields.String(required=True, data_key="endIconConfig", validate=verify_exist)

    @post_load()
    def explain(self, data, **kwargs):
        data = super().explain(data, **kwargs)
        end_config_path = data.get("end_icon_config")
        start_icon_config = data.get("start_icon_config")
        data = self._get_data(data, end_config_path, "end_icon")
        return self._get_data(data, start_icon_config, "start_icon")


class OcrTestSchema(Schema):
    input_image = fields.Method(deserialize="load_picture", data_key="inputImgFile", required=True)
    config_file = fields.Method(deserialize="load_config", data_key="configFile", required=False)
    ocr_choice = fields.String(data_key="ocrChoice", required=False)

    def load_config(self, value):
        value.save(f"{value.filename}")
        with open(f"{value.filename}", "r") as f:
            content = json.load(f)
        os.remove(value.filename)
        return content

    def load_picture(self, value):
        value.save(f"{value.filename}")
        return f"{value.filename}"

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        if data.get("config_file") is not None:
            area = data.get("config_file")
            areas = [area["area" + str(i)] for i in range(1, len(area.keys())) if
                     "area" + str(i) in area.keys()]
            data["areas"] = areas if areas != [] else [[1, 1, 1, 1]]
        return data


class IconTestSchema(OcrTestSchema):
    config_area = fields.Method(deserialize="load_config", data_key="configArea", required=False)

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        area = data.get("config_file")
        areas = [area["area" + str(i)] for i in range(1, len(area.keys())) if
                 "area" + str(i) in area.keys()]
        threshold = float(area.get("threshold", 0.99))
        data["areas"] = areas if areas != [] else [[1, 1, 1, 1]]
        data["threshold"] = threshold
        crop_area = data.get("config_area")
        areas = [crop_area["area" + str(i)] for i in range(1, len(crop_area.keys())) if
                 "area" + str(i) in crop_area.keys()] if crop_area is not None else []
        data["crop_areas"] = areas if areas != [] else [[1, 1, 1, 1]]
        return data


class SimpleSchema(Schema):
    outputPath = fields.String(required=True)
    adbCommand = fields.String(required=True, validate=verify_has_grep)


def has_format(path: str):
    part_list = path.split(".")
    if len(part_list) < 2 or part_list[-1].lower() not in ("mp4", "jpg"):
        raise ValidationError('picture or video should have .mp4 or .jpg')


class SimpleVideoPullSchema(Schema):
    # outputPath = fields.String(required=True)
    adbCommand = fields.String(required=True)
    fileName = fields.String(required=True, validate=has_format)


class PerformanceSchemaCompare(Schema):
    config = fields.String(data_key="configArea")

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        try:
            with open(data.get('config'), "r") as json_file:
                json_data = json.load(json_file)
                areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                         "area" + str(i) in json_data.keys()]
                threshold = float(json_data.get("threshold", 0.99))
            data["areas"] = areas if areas != [] else [[1, 1, 1, 1]]
            data["threshold"] = threshold
            return data
        except (FileNotFoundError,TypeError):
            data["areas"] = [[0, 0, 1, 1]]
            data["threshold"] = 0.99
            return data


class PerformanceSchemaFps(PerformanceSchemaCompare):
    fps = fields.Int(required=True)


class PerformanceSchema(PerformanceSchemaCompare):
    icon_config = fields.String(required=True, data_key="configFile", validate=verify_exist)
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(verify_exist, verify_image))

    @post_load()
    def explain(self, data, **kwargs):
        data = super().explain(data, **kwargs)
        with open(data.get('icon_config'), "r") as json_file_icon:
            json_data_icon = json.load(json_file_icon)
            icon_areas = [json_data_icon["area" + str(i)] for i in range(1, len(json_data_icon.keys())) if
                          "area" + str(i) in json_data_icon.keys()]
            icon_threshold = float(json_data_icon.get("threshold", 0.99))
        data["icon_areas"] = icon_areas if icon_areas != [] else [[1, 1, 1, 1]]
        data["threshold"] = icon_threshold
        return data
