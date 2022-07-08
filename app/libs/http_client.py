import logging
import time
from collections import namedtuple
from json import JSONDecodeError

import requests

from app.config import setting
from app.config.log import TOTAL_LOG_NAME
from app.execption.inner.total import FilterUniqueKeyError, RequestMethodError
from app.execption.outer.error_code.total import ServerError, RequestException
from app.libs.func_tools import run_time

METH_GET = 'GET'
METH_DELETE = 'DELETE'
METH_OPTIONS = 'OPTIONS'
METH_PATCH = 'PATCH'
METH_POST = 'POST'
METH_PUT = 'PUT'

METH_ALL = {METH_GET, METH_DELETE, METH_OPTIONS, METH_PATCH, METH_POST, METH_PUT}

logger = logging.getLogger(TOTAL_LOG_NAME)


def _parse_url(url, ip=None):
    if not url.startswith("http") and ip is None:
        # app = current_app._get_current_object() # 在多线程下,线程隔离 current_app 获取不到app 对象 需要_get_current_object()
        url = f"{setting.REEF_URL}{url}"
    elif not url.startswith("http"):
        url = f"{ip}{url}"
    return url


def request_file(url, method="GET", **kwargs):
    return requests.request(method, _parse_url(url), **kwargs)


def _response_exec(response, filter_unique_key, error_log_hide, **kwargs):
    """
        1 :  known response error
        2 : success
        raise error : unknown response error


        filter_unique_key 作用：
        reef 存在api 例如通过device_label搜索但是但会list,但其实肯定只有一个的情况，因此需要做转化:
        {
            "devices": [
                {
                "cabinet": null,                                        {
                    "device_name": null,                                    "cabinet": null,
                    "id": 21,                          ========>            "device_name": null,
                    "ip_address": "10.80.3.12",                             "id": 21,
                    "tempport": []                                          "ip_address": "10.80.3.12",
                }                                                           "tempport": []
            ]                                                           }
        }
    :param response:
    :return:
    """
    if 400 <= response.status_code < 500:
        try:
            error = response.json()
            if isinstance(error, dict) and error.get("error_code"):  # coral 内部的api error massage 会携带 error_code
                return 1, error
            if not error_log_hide:
                logger.error(f"_response_exec exception: url: {response.url} detail: {error}")
            raise RequestException(description=f"url: {response.url} detail: {error}", code=response.status_code)
        except JSONDecodeError:
            logger.error(f"response data is not json format, "
                         f"url: {response.url} status_code: {response.status_code} detail: {getattr(response,'content', response)}")
            raise ServerError()
    try:
        result: dict = response.json()  # result 默认返回json
    except Exception:
        return 2, {}
    if filter_unique_key:
        parse_res = list(result.values())
        if parse_res == [[]]:  # 没获取到资源
            raise RequestException(description=f"url: {response.url} detail: no receive resource", code=404)
        try:
            result = parse_res.pop().pop()
        except AttributeError:
            raise FilterUniqueKeyError('set filter_unique_key is true load to response data format error ')

    return 2, result


def reason_decode(reason):
    if isinstance(reason, bytes):
        try:
            return reason.decode('utf-8')
        except UnicodeDecodeError:
            return reason.decode('iso-8859-1')
    else:
        return reason


def request_with_response_detail(method="GET", url="", retry=3, filter_unique_key=False, error_log_hide=False,
                                 **kwargs):
    """
        内部的api 请求成功或则失败默认都是返回json

        1 :  known response error
        2 : success
        raise error : unknown response error
    """
    if method.upper() not in METH_ALL:
        raise RequestMethodError("request method error")

    # 500及以上错误和requests请求错误异常需要重试
    # retry值 大于等于一
    ip = kwargs.pop("ip") if kwargs.get("ip") else None
    for i in range(retry):
        request_error = None  # 用于记录最后一次request 内部未知异常造成的Exception
        try:
            response = requests.request(method, _parse_url(url, ip), timeout=120.0, **kwargs)
        except Exception as e:
            request_error = e
            response = namedtuple('Response', ['reason', 'status_code'])(str(e), 504)
        else:
            if response.status_code < 500:
                return _response_exec(response, filter_unique_key, error_log_hide)
        logger.error(f"requests failed  request(method:{method},url:{url},arg:{kwargs} "
                     f"response(reason:{response.reason},status_code:{response.status_code}),"
                     f"current number of requests:{i + 1},try to retry.")
        time.sleep(1)

    if request_error is not None:
        raise ServerError(description=str(request_error))  # 针对 retry 依旧处于request 内部未知异常造成的Exception的处理
        # 针对 retry 依旧处于 500 以上的异常的处理
    raise ServerError(description=reason_decode(response.reason), code=response.status_code)


def request_with_status(method="GET", url="", **kwargs):
    status, result = request_with_response_detail(method, url, **kwargs)
    if status == 1:
        return result["error_code"]
    elif status == 2:
        return result


@run_time
def request(method="GET", url="", **kwargs):
    status, result = request_with_response_detail(method, url, **kwargs)
    if status == 1:
        logger.error(f"request exception: url: {url} detail: {result}")
        raise RequestException(description=f"url:{url} detail: {result}")
    elif status == 2:
        return result


if __name__ == '__main__':

    a = requests.get(
        url="http://www.baidu.com")
    print(a.json())
    # r = requests.request(method="POST", url='http://httpbin.org/put', data=[{'key': 'value'}])
    # print(a)
    # a = request(url="https://api.github.com/users/octocat/received_events")
    # a = request_with_response_detail(url="http://10.80.2.138:8000/api/v1/cedar/device/2/?fields=instance_psort")
    # a = request(url="http://10.80.2.138:8000/api/v1/cedar/android_versiosn/", method="POST", json={"versklion": "gggg"})
    # a = request(url="http://10.80.2.138:8000/api/v1/cedar/android_versiosn/", method="POST", json={"versklion": "gggg"})
    # a = request_with_response_detail(url="http://10.80.2.138:5438/api/v1/cedar/android_version/", method="POST",
    #                                  json={"versklion": "gggg"})
    # a = requests.post(url="http://10.80.3.100:10810/", json=v)
    # print(a)
