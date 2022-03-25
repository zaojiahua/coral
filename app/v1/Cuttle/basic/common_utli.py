import cv2
import numpy as np

from app.execption.outer.error_code.imgtool import ColorPositionCrossMax
from app.v1.Cuttle.basic.setting import blur_signal


def get_file_name(path):
    return ".".join(path.split(".")[:-1])


def adb_unit_maker(cmd_list, device_label, connect_number, timeout=None, max_retry_time=None, **kwargs):
    # 由于新增僚机adb有线连接可能，需要将原有复合unit内所有adb部分增加前置层
    # 缓存内僚机存储形式确定好之后需要对应修改此方法
    from app.v1.device_common.device_model import Device
    ip = Device(pk=device_label).connect_number
    request_body = {
        "ip_address": ip,
        "device_label": device_label,
        "execCmdList": [f"adb -s {connect_number} {cmd}" if "<sleep>" not in cmd else cmd for cmd in cmd_list]
    }
    if timeout is not None:
        request_body['timeout'] = timeout
    if max_retry_time is not None:
        request_body['max_retry_time'] = max_retry_time
    return request_body


def handler_exec(request_body, handler_name):
    from app.v1.Cuttle.basic.basic_views import UnitFactory
    response = UnitFactory().create(handler_name, request_body)
    return response.get("result")


def threshold_set(threshold):
    return (1 - threshold) * 100 * 15


# 与逻辑 非
def precise_match_not(words_list, identify_words_list):
    return 1 if set(identify_words_list) & set(words_list) else 0


# 与逻辑 非 模糊
def blur_match_not(words_list, identify_words_list):
    for word in words_list:
        for req_word in identify_words_list:
            if word in req_word:
                return 1
    return 0


# 与逻辑 模糊
def blur_match(words_list, identify_words_list):
    for word in set(words_list):
        for indentify_word in set(identify_words_list):
            if word in indentify_word:
                break
        else:
            return 1
    return 0


# 与逻辑
def precise_match(required_words_list, identify_words_list):
    return 0 if set(required_words_list).issubset(set(identify_words_list)) else 1


# 或逻辑
def precise_or(required_words_list, identify_words_list):
    return 0 if set(identify_words_list) & set(required_words_list) else 1


# 或逻辑 模糊
def blur_or(words_list, identify_words_list):
    for word in words_list:
        for req_word in identify_words_list:
            if word in req_word:
                return 0
    return 1


# 或逻辑 非
def precise_or_not(required_words_list, identify_words_list):
    for word in set(required_words_list):
        for indentify_word in set(identify_words_list):
            if word == indentify_word:
                break
        else:
            return 0
    return 1


# 或逻辑 模糊 非
def blur_or_not(required_words_list, identify_words_list):
    for word in set(required_words_list):
        for indentify_word in set(identify_words_list):
            if word in indentify_word:
                break
        else:
            return 0
    return 1


# 合并所有的逻辑判断
def condition_judge(is_blur, is_not, required_words_list, identify_words_list):
    is_and = True
    # 或逻辑统一放到这里 其实与也应该放到一块，但是有旧代码，先不动，不可能同时有与和或
    if len(required_words_list) > 0:
        or_meta_word = '/'
        if or_meta_word in required_words_list[0]:
            required_words_list = required_words_list[0].split(or_meta_word)
            is_and = False
    function_name = ('blur' if is_blur else 'precise') + '_' + ('match' if is_and else 'or') + ('_not' if is_not else '')
    print(function_name, '*' * 10)
    return globals()[function_name](required_words_list, identify_words_list)


def judge_pic_same(path_1, path_2):
    src_1 = cv2.imread(path_1)
    src_2 = cv2.imread(path_2)
    if (src_1 is not None and src_2 is not None and src_1.shape != src_2.shape) or src_1 is None or src_2 is None:
        return False
    difference = cv2.subtract(src_1, src_2)
    return np.count_nonzero(difference) < (src_1.shape[0] * src_1.shape[1]) / 2000


def check_color_by_position(src, x, y):
    try:
        return src[x][y]
    except KeyError:
        raise ColorPositionCrossMax


def suit_for_blur(exec_content):
    key = "requiredWords" if exec_content.get("requiredWords") else "exceptWords"
    is_blur = True if exec_content.get(key, "").startswith(blur_signal) else False
    exec_content[key] = exec_content.get(key, "").replace(blur_signal, "")
    return exec_content, is_blur
