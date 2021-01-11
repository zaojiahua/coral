import os
import random
import time
import traceback

import cv2
import imageio
import numpy as np

from app.execption.outer.error_code.imgtool import OcrParseFail, VideoKeyPointNotFound, RecordWordsFindNoWords
from app.v1.Cuttle.basic.calculater_mixin.area_selected_calculater import AreaSelectedMixin
from app.v1.Cuttle.basic.calculater_mixin.color_calculate import ColorMixin
from app.v1.Cuttle.basic.calculater_mixin.compare_calculater import FeatureCompareMixin
from app.v1.Cuttle.basic.calculater_mixin.precise_calculater import PreciseMixin
from app.v1.Cuttle.basic.calculater_mixin.test_calculater import TestMixin
from app.v1.Cuttle.basic.common_utli import get_file_name, threshold_set
from app.v1.Cuttle.basic.coral_cor import Complex_Center
from app.v1.Cuttle.basic.image_schema import ImageSchema, ImageBasicSchema, VideoWordsSchema, \
    VideoPicSchema, ImageOutPutSchema
from app.v1.Cuttle.basic.operator.camera_operator import ImageNumberFile, FpsMax, CameraMax
from app.v1.Cuttle.basic.operator.handler import Handler, Abnormal
from app.v1.Cuttle.basic.setting import bounced_words, icon_threshold, icon_threshold_camera, icon_rate, BIAS, \
    Continues_Number

VideoSearchPosition = 0.5


class ImageHandler(Handler, FeatureCompareMixin, PreciseMixin, AreaSelectedMixin,ColorMixin,TestMixin):
    _error_dict = {
        "configFile": -22,
        "inputImgFile": -23,
        "referImgFile": -24,
        "identifyIconFail": -25,
        "configArea": -26
    }
    # mark 为int 因为img func 返回int
    process_list = [Abnormal(mark=1, method="clear", code=1),
                    Abnormal(mark=2, method="clear", code=0)]

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.skip_list.extend(AreaSelectedMixin.skip_list)


    def img_compare_func3(self, exec_content, **kwargs) -> int:
        # 均值方差对比方法
        data = self._validate(exec_content, ImageSchema)
        for area in data.get("areas"):
            result = self.numpy_array(self._crop_image(data.get("refer_im"), area),
                                      self._crop_image(self.image, area),
                                      threshold_set(data.get("threshold", 0.99)))
            if result != 0:
                return result
        return 0

    def identify_icon(self, exec_content, is_write_file=True) -> int:
        # surf特征找图标方法 （返回类型特殊）
        data = self._validate(exec_content, ImageSchema)

        result = self.identify_icon_point(self._crop_image(data.get("input_im"), [1, 1, 1, 1]),
                                          self._crop_image(data.get("refer_im"), data.get("areas")[0]))
        if data.get("output_path"):
            point_x, point_y = result
            self._write_down(data.get("output_path"), f"{round(point_x, 2)} {round(point_y, 2)}")
        point_x, point_y = result
        # extra_result 的结果会最终合并到unit的结果中去
        self.extra_result = {"point_x": float(point_x), "point_y": float(point_y)}
        return 0

    def has_icon(self, exec_content) -> int:
        # 判断所选择区域内有指定图标
        data = self._validate(exec_content, ImageSchema)
        feature_refer = self._crop_image(data.get("refer_im"), data.get("areas")[0])
        feature_point_list = self.shape_identify(cv2.imread(data.get("input_im")), feature_refer)
        from app.v1.device_common.device_model import Device
        threshold = icon_threshold if Device(pk=self._model.pk).has_camera == False else icon_threshold_camera
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{threshold - (1 - data.get('threshold', 0.99)) * icon_rate}")
        return 0 if len(feature_point_list) >= threshold - (1 - data.get("threshold", 0.99)) * icon_rate else 1

    def has_words(self, exec_content) -> int:
        # 判断所选择区域内有指定文字
        words_list, path = self.words_prepare(exec_content, "requiredWords")
        # 此处不传递words给ocr service，避免不确定长度文字对结果的限制（会稍微影响速度）
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip('",.\n') for item in response]
        for word in set(words_list):
            for indentify_word in set(identify_words_list):
                if word in indentify_word:
                    break
            else:
                return 1
        return 0

    def except_words(self, exec_content) -> int:
        # 判断所选择区域内没有有指定文字
        words_list, path = self.words_prepare(exec_content, "exceptWords")
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip('",.\n') for item in response]
        for word in set(words_list):
            for indentify_word in set(identify_words_list):
                if word in indentify_word:
                    return 1
        return 0

    def time_calculate_by_word(self, exec_content):
        # 计算得到起始点到终止点所用时间
        try:
            b = time.time()
            data = self._validate(exec_content, VideoWordsSchema)
            time_persent = self.camera_or_adb()
            start_number = self.find_point(data, self.match_words, "start", 0, target=False)
            end_number = self.search_end(data, start_number, self.match_words)
            print("单位时间:", time_persent, "end number:", end_number, "start number:", start_number)
            self.extra_result = {"time": round((end_number - start_number) * time_persent + BIAS, 2)}
            print("总用时: ", time.time() - b)
            return 0
        except VideoKeyPointNotFound:
            return 1

    def camera_or_adb(self):
        fps = self.video_to_pic(self.video) if os.path.exists(self.video) else FpsMax
        return 1 / fps

    def time_calculate_by_pic(self, exec_content):
        b = time.time()
        data = self._validate(exec_content, VideoPicSchema)
        time_persent = self.camera_or_adb()
        start_number = self.find_point(data, self.match_icon, "start", 0, target=False)
        end_number = self.search_end(data, start_number, self.match_icon)
        print("总用时: ", time.time() - b)
        self.extra_result = {"time": round((end_number - start_number) * time_persent + BIAS, 2)}
        return 0

    def search_end(self, data, start_number, function):
        # 先读取总图片(帧)数
        with open(get_file_name(self.video) + ImageNumberFile) as f:
            total_number = f.read()
        search_position = int(float(total_number) * VideoSearchPosition)
        search_position = start_number + 1 if search_position <= start_number else search_position
        number = self.find_point(data, function, "end", search_position)
        # 分情况搜索
        if number == search_position:
            # 需要向前搜索,查找不匹配帧,搜索范围0.5倍总帧数至已搜寻到的起点帧
            number = self.find_point(data, function, "end", search_position - 1, reverse=True, target=False,
                                     end_position=start_number)
            return number + 1  # 结束帧取向前搜索不一样的后一帧
        elif number > search_position:
            # 找到位置
            return number

    def find_point(self, data, compare_function, point="start", start_point=0, reverse=False, target=True,
                   end_position=0):
        """
        关键帧寻找的核心函数，通过传入的比对函数通过不同方法找寻具体关键帧。
        :param data: 经过验证的数据
        :param point: start/end 标明使用起始/终止特征
        :param compare_function  用来具体比对的函数，比对成功returnTrue，看下一张returnFalse (match_words,match_icon)
        :param start_point:搜寻的起始点
        :param reverse:是否反向
        :param target:寻找第一个匹配点/不匹配点
        :param end_position: 寻找的终点
        :return:图片number
        """
        print("start position:", start_point)
        iter = range(start_point, CameraMax) if not reverse else range(start_point, end_position, -1)
        mark = 0
        try:
            icon = self._crop_image(data.get(f"{point}_image"), data.get(f"{point}_icon_areas", " ")[0])
            if icon is not None:
                cv2.imwrite(os.path.join(self.kwargs.get("work_path"), f"{point}-icon.png"), icon)
            for i in iter:
                input = self._crop_image(get_file_name(self.video) + f"__{i}.png",
                                         data.get(f"{point}_areas")[0])
                path = os.path.join(self.kwargs.get("work_path"), f"crop-{i}.png")
                cv2.imwrite(path, input)
                result = compare_function(data, path, point, icon, target)
                if result is True:
                    print("find one point ones:", i)
                    # 连续两张/多张均匹配成功才确认。待ocr质量提升后可以去掉此环节。
                    real = i - Continues_Number if not reverse else i + Continues_Number
                    if real == mark:
                        return real
                    mark = i
                    continue
                else:
                    continue
            else:
                raise VideoKeyPointNotFound  # 没找到 任务失败
        except AttributeError as e:
            print("in find_point function", repr(e))
            traceback.print_exc()
            raise VideoKeyPointNotFound

    def match_words(self, data, input_path, point, refer=None, target=True):
        # 通过文字匹配单幅图片，return True说明匹配到，False 需要看下一张照片
        with Complex_Center(inputImgFile=input_path, **self.kwargs) as ocr_obj:
            response = ocr_obj.get_result()
        identify_words_list = [item.get("text").strip().strip('",.\n') for item in response]
        response = self.words_judegment(data.get(f"{point}_words"), identify_words_list)
        if target is False:
            response = bool(1 - response)
        return response

    def match_icon(self, data, input_path, point, refer, target=True):
        feature_point_list = self.shape_identify(cv2.imread(input_path), refer)
        from app.v1.device_common.device_model import Device
        threshold_level = icon_threshold if Device(pk=self._model.pk).has_camera == False else icon_threshold_camera
        threshold = int((1 - data.get(f"{point}_threshold", 0.99)) * icon_rate)
        self._model.logger.info(
            f"feature point number:{len(feature_point_list)},threshold:{threshold_level - threshold}")
        response = True if len(feature_point_list) >= (threshold_level - threshold) else False
        if target is False:
            response = bool(1 - response)
        return response

    def words_judegment(self, words: str, identify_words_list: list):
        if "^" in words:
            required_words_list = words.split("^")
            for word in identify_words_list:
                if word in required_words_list:
                    return True
            return False
        else:
            required_words_list = words.split("&")
            for word in required_words_list:
                if word not in identify_words_list:
                    return False
            return True

    def video_to_pic(self, video_file):
        start = time.time()
        reader = imageio.get_reader(video_file)
        fps = reader.get_meta_data()['fps']
        drop = int(fps / FpsMax) if fps / 2 > FpsMax else 1
        num = 0
        try:
            for index in range(0, 10000, drop):
                im = reader.get_data(index)
                img = cv2.cvtColor(im, cv2.COLOR_RGB2BGR)
                new_name = get_file_name(self.video) + f"__{num}.png"
                cv2.imwrite(new_name, img)
                num += 1
        except IndexError:
            # 最后一张图放入类属性，用于T-Guard 排除干扰
            self.image = new_name
            pass
        with open(get_file_name(self.video) + ImageNumberFile, "w") as f:
            f.write(str(num - 1))
        print("fps:", int(fps / drop))
        print("拆分视频用时：", time.time() - start)
        return int(fps / drop)

    def words_prepare(self, exec_content, key):
        data = self._validate(exec_content, schema=ImageBasicSchema)
        words_list = exec_content.get(key).split(",")
        input = self._crop_image(self.image, data.get("areas")[0])
        path = os.path.join(self.kwargs.get("work_path"), f"ocr-{random.random()}.png")
        cv2.imwrite(path, input)
        return words_list, path

    def clear(self, *args):
        with Complex_Center(inputImgFile=self.image, **self.kwargs) as ocr_obj:
            ocr_obj.get_result(parse_function=self._parse_function)
            if ocr_obj.result == 0:
                ocr_obj.point()
                return 0
            return ocr_obj.result

    def model_order(self):
        # 暂时不对image进行排队处理
        pass

    #   辅助函数
    def _validate(self, exec_content, schema):
        data = schema().load(exec_content)
        self.video = data.get("video_file")
        from app.v1.device_common.device_model import Device
        name = ""
        if Device(pk=self._model.pk).has_camera and self.video is not None:
            with open(get_file_name(self.video) + ImageNumberFile) as f:
                total_number = f.read()
            name = get_file_name(self.video) + f"__{int(total_number) - 1}.png"
        self.image = data.get("input_im", name)

        return data

    @staticmethod
    def _parse_function(result_list):
        for i in result_list:
            for word in bounced_words:
                if word == i.get("text"):
                    return float(i.get("cx")), float(i.get("cy"))
        else:
            raise OcrParseFail

    def _crop_image(self, image_path, area):
        try:
            image = cv2.imread(image_path)
            if area[3] == area[2] == 0.99999 and area[0] == area[0] == 0:
                return image
            if any(np.array(area) < 1):
                h, w = image.shape[:2]
                area = [int(i) if i > 0 else 0 for i in [area[0] * w, area[1] * h, area[2] * w, area[3] * h]]
            elif all(np.array(area) == 1):
                return image
            return image[area[1]:area[3], area[0]:area[2]]
        except TypeError as e:
            return None

    def _crop_image_and_save(self, image_path, area):
        src = self._crop_image(image_path, area)
        if src is not None:
            new_path = ".".join(image_path.split(".")[:-1]) + "-crop.jpg"
            cv2.imwrite(new_path, src)
            return new_path

    def _write_down(self, file, context):
        fp = open(file, 'w')
        fp.write(context)
        fp.close()
        return 0

    def record_words(self, exec_content) -> int:
        data = self._validate(exec_content, ImageSchema)
        path = self._crop_image_and_save(data.get("input_im"), data.get("areas")[0])
        with Complex_Center(inputImgFile=path, **self.kwargs) as ocr_obj:
            self.image = path
            result = ocr_obj.get_result()
            if not isinstance(result, list) or len(result) == 0:
                raise RecordWordsFindNoWords
            words = result[0].get("text")
            self._write_down(data.get("output_path"), f"{words}")
        return 0

    def is_pure(self, exec_content):
        data = self._validate(exec_content, ImageBasicSchema)
        feature_refer = self._crop_image(data.get("refer_im"), data.get("areas")[0])
