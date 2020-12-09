import abc
import collections
import copy
import time

from marshmallow import ValidationError

from app.execption.outer.error_code.adb import UnitBusy, NoContent
from app.libs.functools import method_dispatch
from app.libs.log import setup_logger
from app.v1.Cuttle.basic.setting import normal_result

Abnormal = collections.namedtuple("Abnormal", ["mark", "method", "code"])
Standard = collections.namedtuple("Standard", ["mark","code"])

Dummy_model = collections.namedtuple("Dummy_model", ["is_busy", "pk", "logger"])


class Handler():
    process_list = []
    skip_list = []
    standard_list = []

    def __init__(self, *args, **kwargs):
        self._model = kwargs.get("model", Dummy_model(False, 0, setup_logger(f'dummy', 'dummy.log')))
        # execCmdList 对应adb格式的创建，execCmdDict对应其他格式，此处为主要执行内容
        content = kwargs.get("execCmdList", kwargs.get("execCmdDict"))
        self.exec_content = content.copy() if content is not None else None
        self.timeout = 40
        self.kwargs = kwargs
        self.extra_result = {}

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
            result = self.func(self.exec_content, **kwargs)
        except ValidationError as e:
            print(f"error message:{e.messages}")
            return {"result": self._error_dict[list(e.messages.keys())[0]]}
        response = {"result": self.after_execute(result, self.func.__name__)}
        if self.extra_result:
            response.update(self.extra_result)
        return response

    @method_dispatch
    def after_execute(self, result: int, funcname) -> int:
        # 此处参数result可能为str(adb，complex),int(complex,hand,imgtool,camera)但返回值一定归结与int
        # 默认后处理方法，对abnormal对象，根据条件进行处理，可按需要继承重写
        if funcname not in self.skip_list:
            for abnormal in self.process_list:
                if result == abnormal.mark:
                    self._model.logger.info(f"after execute result: {self._model}")
                    getattr(self, abnormal.method)(result)
                    return abnormal.code
        result = result if isinstance(result, int) else 0
        return result

    @after_execute.register(str)
    def _(self, result, funcname):
        # 处理字符串格式的返回，流程与int型类似，去abnormal中进行匹配，并执行对应方法
        if funcname not in self.skip_list:
            for abnormal in self.process_list:
                if isinstance(abnormal.mark,str)and abnormal.mark in result:
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


class ListHandler(Handler):

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child')
        assert self.child is not None, '`child` is a required argument.'
        super(ListHandler, self).__init__(*args, **kwargs)

    def execute(self, **kwargs):
        flag = 0
        for single_cmd in copy.deepcopy(self.exec_content):
            try:
                self.child.exec_content = single_cmd
                result = self.child.execute(**kwargs)
                flag = result.get("result", -1) if result.get("result") != 0 else flag
            except NoContent:
                continue
        return_vaule = {"result": 0} if flag == 0 else {"result": flag}
        self.after_unit()
        return return_vaule

    def after_unit(self):
        self.child.after_unit()
        pass
