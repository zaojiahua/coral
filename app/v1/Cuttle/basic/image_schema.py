import json
import os

import cv2
from marshmallow import Schema, fields, ValidationError, post_load, INCLUDE


def vertify_exist(path):
    if not os.path.exists(path):
        raise ValidationError('path not exist')


def verify_image(image_path):
    im = cv2.imread(image_path)
    if im is None:
        raise ValidationError('image not correct format')
    s = im.shape[0] * im.shape[1]
    if s < 100:
        raise ValidationError('image need bigger size ')


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


class IconTestSchema(Schema):
    config_area = fields.Method(deserialize="load_config", data_key="configArea",required=False)
    input_image = fields.Method(deserialize="load_picture", data_key="inputImgFile")
    config_file = fields.Method(deserialize="load_config", data_key="configFile")

    def load_config(self, value):
        value.save(f"{value.filename}")
        with open(f"{value.filename}", "r") as f:
            content = json.load(f)
        os.remove(value.filename)
        return content

    def load_picture(self, value):
        value.save(f"{value.filename}")
        return f"{value.filename}"

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
