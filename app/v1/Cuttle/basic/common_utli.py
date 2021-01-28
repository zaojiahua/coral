import cv2
import numpy as np

from app.execption.outer.error_code.imgtool import ColorPositionCrossMax


def get_file_name(path):
    return ".".join(path.split(".")[:-1])


def adb_unit_maker(cmd_list, device_label, connect_number):
    # 由于新增僚机adb有线连接可能，需要将原有复合unit内所有adb部分增加前置层
    # 缓存内僚机存储形式确定好之后需要对应修改此方法
    from app.v1.device_common.device_model import Device
    ip = Device(pk=device_label).ip_address
    request_body = {
        "ip_address": ip,
        "device_label": device_label,
        "execCmdList": [f"adb -s {connect_number} {cmd}" if "<sleep>" not in cmd else cmd for cmd in cmd_list]
    }
    return request_body


def handler_exec(request_body, handler_name):
    from app.v1.Cuttle.basic.basic_views import UnitFactory
    response = UnitFactory().create(handler_name, request_body)
    return response.get("result")


def threshold_set(threshold):
    return (1 - threshold) * 100 * 15


def precise_match(identify_words_list, words_list):
    for word in set(words_list):
        for indentify_word in set(identify_words_list):
            if word == indentify_word:
                break
        else:
            return 1
    return 0


def blur_match(identify_words_list, words_list):
    for word in set(words_list):
        for indentify_word in set(identify_words_list):
            if word in indentify_word:
                break
        else:
            return 1
    return 0


def judge_pic_same(path_1, path_2):
    src_1 = cv2.imread(path_1)
    src_2 = cv2.imread(path_2)
    difference = cv2.subtract(src_1, src_2)
    return np.count_nonzero(difference) < (src_1.shape[0] * src_1.shape[1]) / 2000


def check_color_by_position(src, x, y):
    try:
        return src[x][y]
    except KeyError:
        raise ColorPositionCrossMax
