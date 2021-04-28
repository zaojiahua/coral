import json
import os

import cv2
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE


def vertify_exist(path):
    if not os.path.exists(path):
        raise ValidationError('path not exist')


def vertify_format(str):
    coor_list = str.strip().split(" ")
    if len(coor_list) != 2:
        raise ValidationError('params wrong format --only one blank')
    try:
        for coor in coor_list:
            if float(coor) > 5000:
                raise ValidationError('need isdigit(<5000) parameters ')
    except ValueError:
        raise ValidationError('color coordinate should be digit')


def vertify_not_relative_coor(str):
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


def vertify_has_grep(cmd):
    if not "grep" in cmd and not "findstr" in cmd:
        raise ValidationError('input adb order should have "grep"/"findstr" ')


class ImageOriginalSchema(Schema):
    config = fields.String(required=True, data_key="configFile", validate=vertify_exist)

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
        data["areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
        data["threshold"] = threshold
        return data


class ImageBasicSchema(ImageOriginalSchema):
    input_im = fields.String(required=True, data_key="inputImgFile", validate=(vertify_exist, verify_image))
    output_path = fields.String(data_key="outputPath")


class ImageOutPutSchema(ImageOriginalSchema):
    output_path = fields.String(data_key="outputPath")
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(vertify_exist, verify_image))


class ImageSchema(ImageBasicSchema):
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(vertify_exist, verify_image))


class ImageRealtimeSchema(ImageBasicSchema):
    input_im_2 = fields.String(required=True, data_key="inputImgFile2", validate=(vertify_exist, verify_image))


class ImageColorSchema(ImageBasicSchema):
    color = fields.String(required=True, data_key="color")


class ImageMainColorSchema(ImageColorSchema):
    percent = fields.String(required=True, data_key="percent")


class ImageColorRelativePositionSchema(ImageSchema):
    requiredWords = fields.String(required=True, data_key="requiredWords")
    xyShift = fields.String(required=True, data_key="xyShift", validate=vertify_format)
    position = fields.String(required=True, data_key="position", validate=(vertify_not_relative_coor, vertify_format))


class ImageAreaSchema(ImageSchema):
    area_config = fields.String(required=True, data_key="configArea", validate=vertify_exist)

    @post_load()
    def explain(self, data, **kwargs):
        crop_area_path = data.get("area_config")
        data = super().explain(data, **kwargs)
        with open(crop_area_path, "r") as json_file:
            json_data = json.load(json_file)
            areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                     "area" + str(i) in json_data.keys()]
        data["crop_areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
        return data


class ImageAreaWithoutInputSchema(ImageSchema):
    area_config = fields.String(required=True, data_key="configArea", validate=vertify_exist)
    input_im = fields.String(required=False, data_key="inputImgFile")

    @post_load()
    def explain(self, data, **kwargs):
        crop_area_path = data.get("area_config")
        data = super().explain(data, **kwargs)
        with open(crop_area_path, "r") as json_file:
            json_data = json.load(json_file)
            areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                     "area" + str(i) in json_data.keys()]
        data["crop_areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
        return data


class VideoBaseSchema(Schema):
    video_file = fields.String(required=True, data_key="videoFile")
    start_config = fields.String(required=True, data_key="startConfig", validate=vertify_exist)
    end_config = fields.String(required=True, data_key="endConfig", validate=vertify_exist)

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
        data[f"{prex}_areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
        data[f"{prex}_threshold"] = threshold
        return data


class VideoWordsSchema(VideoBaseSchema):
    start_words = fields.String(required=True, data_key="startWords")
    end_words = fields.String(required=True, data_key="endWords")


class VideoPicSchema(VideoBaseSchema):
    end_image = fields.String(required=True, data_key="endImage", validate=(vertify_exist, verify_image))
    start_image = fields.String(required=True, data_key="startImage", validate=(vertify_exist, verify_image))
    start_icon_config = fields.String(required=True, data_key="startIconConfig", validate=vertify_exist)
    end_icon_config = fields.String(required=True, data_key="endIconConfig", validate=vertify_exist)

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
            data["areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
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
        data["areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
        data["threshold"] = threshold
        crop_area = data.get("config_area")
        areas = [crop_area["area" + str(i)] for i in range(1, len(crop_area.keys())) if
                 "area" + str(i) in crop_area.keys()] if crop_area is not None else []
        data["crop_areas"] = areas if areas != [] else [[1, 1, 1, 1]]
        return data


class SimpleSchema(Schema):
    outputPath = fields.String(required=True)
    adbCommand = fields.String(required=True, validate=vertify_has_grep)


def has_format(path: str):
    part_list = path.split(".")
    if len(part_list) < 2 or part_list[-1].lower() not in ("mp4", "jpg"):
        raise ValidationError('picture or video should have .mp4 or .jpg')


class SimpleVideoPullSchema(Schema):
    # outputPath = fields.String(required=True)
    adbCommand = fields.String(required=True)
    fileName = fields.String(required=True, validate=has_format)


class PerformanceSchemaCompare(Schema):
    config = fields.String(required=True, data_key="configArea", validate=vertify_exist)

    class Meta:
        unknown = INCLUDE

    @post_load()
    def explain(self, data, **kwargs):
        with open(data.get('config'), "r") as json_file:
            json_data = json.load(json_file)
            areas = [json_data["area" + str(i)] for i in range(1, len(json_data.keys())) if
                     "area" + str(i) in json_data.keys()]
            threshold = float(json_data.get("threshold", 0.99))
        data["areas"] = areas if areas is not [] else [[1, 1, 1, 1]]
        data["threshold"] = threshold
        return data


class PerformanceSchemaFps(PerformanceSchemaCompare):
    fps = fields.Int(required=True)



class PerformanceSchema(PerformanceSchemaCompare):
    icon_config = fields.String(required=True, data_key="configFile", validate=vertify_exist)
    refer_im = fields.String(required=True, data_key="referImgFile", validate=(vertify_exist, verify_image))

    @post_load()
    def explain(self, data, **kwargs):
        data = super().explain(data, **kwargs)
        with open(data.get('icon_config'), "r") as json_file_icon:
            json_data_icon = json.load(json_file_icon)
            icon_areas = [json_data_icon["area" + str(i)] for i in range(1, len(json_data_icon.keys())) if
                          "area" + str(i) in json_data_icon.keys()]
            icon_threshold = float(json_data_icon.get("threshold", 0.99))
        data["icon_areas"] = icon_areas if icon_areas is not [] else [[1, 1, 1, 1]]
        data["threshold"] = icon_threshold
        return data
