import collections
import copy
import re
import time
import traceback
import random

import func_timeout
from func_timeout import func_set_timeout
from marshmallow import ValidationError

from app.execption.outer.error_code.adb import UnitBusy, NoContent
from app.libs.functools import method_dispatch
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.setting import normal_result, KILL_SERVER, START_SERVER, SERVER_OPERATE_LOCK, \
    NORMAL_OPERATE_LOCK, adb_cmd_prefix, unlock_cmd
from app.execption.outer.error_code.imgtool import DetectNoResponse
from app.v1.eblock.config.setting import DEFAULT_TIMEOUT, ADB_DEFAULT_TIMEOUT
from app.config.ip import ADB_TYPE

Abnormal = collections.namedtuple("Abnormal", ["mark", "method", "code"])
Standard = collections.namedtuple("Standard", ["mark", "code"])

# 虚拟model，用来给没有model对象的赋值。
Dummy_model = collections.namedtuple("Dummy_model", ["is_busy", "pk", "logger"])


class Handler():
    # process_list里面放具体的Abnormal namedtuple，用来根据结果内容做后处理（Tguard介入/adb 重连/解析获取电量信息等..）
    process_list = []
    # skip_list 里放对应放方法名，用于跳过后处理机制（通常需要跳过的后处理为Tguard）
    skip_list = []
    # standard_list 里放Standard namedtuple，用来根据执行结果（字符串等情况）设定 unit结果
    standard_list = []

    skip_retry_list = ["end_point_with_icon", "end_point_with_icon_template_match", "end_point_with_changed",
                       "end_point_with_fps_lost","initiative_remove_interference"]

    def __init__(self, *args, **kwargs):
        self._model = kwargs.get("model", Dummy_model(False, 0, setup_logger(f'dummy', 'dummy.log')))
        # execCmdList 对应adb格式的创建，execCmdDict对应其他格式，此处为主要执行内容
        content = kwargs.get("execCmdList", kwargs.get("execCmdDict"))
        self.exec_content = content.copy() if content is not None else None
        self.timeout = 40
        self.kwargs = kwargs
        self.handler_timeout = self.kwargs.get('timeout') or DEFAULT_TIMEOUT
        self.str_handler_timeout = self.kwargs.get('timeout') or ADB_DEFAULT_TIMEOUT
        self.extra_result = {}
        self.optional_input_image = self.kwargs.get('optional_input_image') or 0

    def __new__(cls, *args, **kwargs):
        if kwargs.pop('many', False):
            return cls.many_init(*args, **kwargs)
        return super().__new__(cls)

    @classmethod
    def many_init(cls, *args, **kwargs):
        # 抄drf的一个设计，实际创建的是listHandler，并传入自身作为child
        kwargs["child"] = cls(*args, **kwargs)
        return ListHandler(*args, **kwargs)

    def __enter__(self):
        # self.model_order()
        return self

    def model_order(self):
        # 当需要自定义排序规则时，需要重写此方法
        timeout = 0
        while self._model.is_busy == True:
            time.sleep(1)
            timeout += 1
            if timeout >= self.timeout:
                self._model.logger.error(
                    f"unit busy until {self.timeout}s in : {type(self).__name__} for {self._model.pk}")
                raise UnitBusy
        self._model.is_busy = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._model.is_busy = False

    def execute(self, **kwargs) -> dict:
        # 默认执行方法，使用self.func，去执行self.exec_content中内容。
        # 返回 {"result":int}  也可能多出其他项目eg： {"result": 0, "point_x": float(point_x), "point_y": float(point_y)}
        (skip, result) = self.before_execute()
        if skip:
            return {"result": result}
        assert (hasattr(self, "func") and hasattr(self, "exec_content")), "func and exec_content should be set"
        try:
            result = self.do(self.exec_content, **kwargs)
        except ValidationError as e:
            try:
                return {"result": self._error_dict[list(e.messages.keys())[0]]}
            except KeyError:
                return {"result": -10000}
        response = {"result": self.after_execute(result, self.func.__name__)}
        if self.extra_result:
            response.update(self.extra_result)
        return response

    @method_dispatch
    def do(self, exec_content, **kwargs):
        @func_set_timeout(timeout=self.handler_timeout)
        def _inner_func():
            # 具体执行方法，这部分处理不是字符串的unit
            return self.func(exec_content, **kwargs)

        return self.retry_timeout_func(_inner_func)

    @do.register(str)
    def _(self, exec_content, **kwargs):
        # 处理content为字符串的unit
        @func_set_timeout(timeout=self.str_handler_timeout)
        def _inner_func():
            return self.str_func(exec_content, **kwargs)

        # 俩种类型的指令互斥
        if ADB_TYPE == 1:
            random_value = random.random()
            kwargs['random_value'] = random_value
            if exec_content == (adb_cmd_prefix + KILL_SERVER) or exec_content == (adb_cmd_prefix + START_SERVER):
                kwargs['target_lock'] = NORMAL_OPERATE_LOCK
                kwargs['lock_type'] = SERVER_OPERATE_LOCK
            else:
                kwargs['target_lock'] = SERVER_OPERATE_LOCK
                kwargs['lock_type'] = NORMAL_OPERATE_LOCK

        def _inner_lock_func():
            try:
                return _inner_func()
            except func_timeout.exceptions.FunctionTimedOut as e:
                # 超时以后需要删除lock
                if kwargs.get('lock_type'):
                    unlock_cmd(keys=[kwargs['lock_type']], args=[kwargs['random_value']])
                raise e

        return self.retry_timeout_func(_inner_lock_func)

    @staticmethod
    def retry_timeout_func(func, max_retry_time=3):
        retry_time = 0
        while retry_time < max_retry_time:
            try:
                return func()
            except func_timeout.exceptions.FunctionTimedOut as e:
                retry_time += 1
                if retry_time == max_retry_time:
                    raise e

    @method_dispatch
    def after_execute(self, result: int, funcname) -> int:
        # 此处参数result可能为str(adb，complex),int(complex,hand,imgtool,camera)但返回值一定归结与int
        # 默认后处理方法，对abnormal对象，根据条件进行处理，可按需要继承重写
        if funcname not in self.skip_list:
            for abnormal in self.process_list:
                if result == abnormal.mark:
                    self._model.logger.info(f"after execute result: {self._model}")
                    try:
                        response = getattr(self, abnormal.method)(result, self.kwargs.get("t_guard"))
                        if response == 0 and funcname not in self.skip_retry_list:
                            return 666
                    except DetectNoResponse as e:
                        raise e
                    except Exception as e:
                        self._model.logger.error(f'tGuard error: {str(e)}')
                        traceback.print_exc()
                    return abnormal.code
        result = result if isinstance(result, int) else 0
        return result

    @after_execute.register(str)
    def _(self, result, funcname):
        # 处理字符串格式的返回，流程与int型类似，去abnormal中进行匹配，并执行对应方法
        if funcname not in self.skip_list:
            for abnormal in self.process_list:
                if isinstance(abnormal.mark, str) and abnormal.mark in result:
                    getattr(self, abnormal.method)(result)
                    return abnormal.code
            for standard in self.standard_list:
                if standard.mark == result:
                    return standard.code
        return 0

    def before_execute(self, **kwargs):
        # 默认的前置处理方法，根据functionName找到对应方法
        opt_type = self.exec_content.pop("functionName")
        self.func = getattr(self, opt_type)
        return normal_result

    def after_unit(self):
        # 整unit完成后需要执行的方法，需要在继承类里自定义
        pass

    def func(self, *args, **kwargs):
        # 真实执行函数，需要在继承类中指定，adb中返回str，其他返回int
        pass

    def _relative_double_point(self):
        regex = re.compile("double_point([\d.]*?) ([\d.]*)")
        result = re.search(regex, self.exec_content)
        x = float(result.group(1))
        y = float(result.group(2))
        if any((0 < x < 1, 0 < y < 1)):
            from app.v1.device_common.device_model import Device
            w = Device(pk=self._model.pk).device_width * x
            h = Device(pk=self._model.pk).device_height * y
            self.exec_content = self.exec_content.replace(result.group(1), str(w), 1)
            self.exec_content = self.exec_content.replace(result.group(2), str(h), 1)
        return normal_result

    def _relative_point(self):
        regex = re.compile("shell input tap ([\d.]*?) ([\d.]*)")
        result = re.search(regex, self.exec_content)
        x = float(result.group(1))
        y = float(result.group(2))
        if any((0 < x < 1, 0 < y < 1)):
            from app.v1.device_common.device_model import Device
            w = Device(pk=self._model.pk).device_width * x
            h = Device(pk=self._model.pk).device_height * y
            self.exec_content = self.exec_content.replace(result.group(1), str(w), 1)
            self.exec_content = self.exec_content.replace(result.group(2), str(h), 1)
        return normal_result

    def _relative_swipe(self):
        # 兼容相对坐标的‘滑动’方法，把执行体内的相对坐标先会换成绝对坐标。
        # 就是按正则找到对应坐标位置，并根据设备分辨率进行替换
        regex = re.compile("shell input swipe ([\d.]*?) ([\d.]*?) ([\d.]*?) ([\d.]*)")
        result = re.search(regex, self.exec_content)
        x1 = float(result.group(1))
        y1 = float(result.group(2))
        x2 = float(result.group(3))
        y2 = float(result.group(4))
        if any((0 < x1 < 1, 0 < y2 < 1, 0 < x2 < 1, 0 < y2 < 1)):
            from app.v1.device_common.device_model import Device
            w1 = Device(pk=self._model.pk).device_width * x1
            h1 = Device(pk=self._model.pk).device_height * y1
            w2 = Device(pk=self._model.pk).device_width * x2
            h2 = Device(pk=self._model.pk).device_height * y2
            self.exec_content = self.exec_content.replace(result.group(1), str(w1), 1)
            self.exec_content = self.exec_content.replace(result.group(2), str(h1), 1)
            self.exec_content = self.exec_content.replace(result.group(3), str(w2), 1)
            self.exec_content = self.exec_content.replace(result.group(4), str(h2), 1)

        return normal_result


class ListHandler(Handler):

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child')
        assert self.child is not None, '`child` is a required argument.'
        super(ListHandler, self).__init__(*args, **kwargs)

    def execute(self, **kwargs):
        flag = 0
        for index, single_cmd in enumerate(copy.deepcopy(self.exec_content)):
            try:
                self.child.exec_content = single_cmd
                kwargs['index'] = index
                kwargs['length'] = len(self.exec_content)
                result = self.child.execute(**kwargs)
                flag = result.get("result", -1) if result.get("result") != 0 else flag
            except NoContent:
                continue
        return_value = {"result": 0} if flag == 0 else {"result": flag}
        self.after_unit()
        return return_value

    def after_unit(self):
        self.child.after_unit()
        pass
