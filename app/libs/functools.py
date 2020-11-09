import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps, partial, singledispatch

from app.config.log import REQUEST_LOG_TIME_STATISTICS
from app.v1.Cuttle.basic.setting import handler_config


def async_timeout(timeout=20):
    def decorate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return ThreadPoolExecutor().submit(partial(func, *args, **kwargs)).result(timeout=timeout)

        return wrapper

    return decorate


def execute_limit(interval_time=300):
    def decorate(func):
        cache = {}

        @wraps(func)
        def decorated_func(*args, **kwargs):
            key = func.__name__
            difference = str(args[0])
            if key + difference in cache.keys():
                if time.time() - cache[key + difference] > interval_time:
                    cache[key + difference] = time.time()
                    func(*args, **kwargs)
            else:
                cache[key + difference] = time.time()
                func(*args, **kwargs)

        return decorated_func

    return decorate


def handler_switcher(func):
    @wraps(func)
    def wrapper(*args, **kw):
        kw.update({"handler": handler_config.get(func.__name__)})
        return func(*args, **kw)

    return wrapper


try:
    from line_profiler import LineProfiler


    def func_line_time(follow=[]):
        def decorate(func):
            @wraps(func)
            def profiled_func(*args, **kwargs):
                try:
                    profiler = LineProfiler()
                    profiler.add_function(func)
                    for f in follow:
                        profiler.add_function(f)
                    profiler.enable_by_count()
                    return func(*args, **kwargs)
                finally:
                    profiler.print_stats()

            return profiled_func

        return decorate

except ImportError:
    def func_line_time(follow=[]):
        def decorate(func):
            @wraps(func)
            def nothing(*args, **kwargs):
                return func(*args, **kwargs)

            return nothing

        return decorate


def method_dispatch(func):
    # 带有self参数的singledispatch, 当升级到py3.8后使用新的singledispatchmethod可代替此方法
    dispatcher = singledispatch(func)

    @wraps(func)
    def wrapper(*args, **kw):
        return dispatcher.dispatch(args[1].__class__)(*args, **kw)

    wrapper.register = dispatcher.register
    return wrapper


def run_time(func):
    def wrapper(*args, **kw):
        local_time = time.time()
        result = func(*args, **kw)
        all_time = time.time() - local_time
        if all_time > 5:
            logging.getLogger(REQUEST_LOG_TIME_STATISTICS).error(f'{kw}, time:{all_time}')
        return result

    return wrapper
