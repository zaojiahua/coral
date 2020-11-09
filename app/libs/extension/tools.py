import importlib
import pkgutil

import pandas as pd

from app.execption.outer import error_code

import inspect

def get_module_from_package(package):
    """
    非递归，值获取package下第一层的module
    """
    prefix = package.__name__ + "."
    return [importlib.import_module(modname) for importer, modname, ispkg in
            pkgutil.iter_modules(package.__path__, prefix) if not ispkg]


def get_classes(module, superclass=object):
    clsmembers = inspect.getmembers(module, inspect.isclass)

    return [_class for (name, _class) in clsmembers if issubclass(_class, superclass)]


def convert_to_html(result, title):
    d = {}
    index = 0
    for t in title:
        d[t] = result[index]
        index = index + 1
    df = pd.DataFrame(d)
    df = df[title]
    h = df.to_html(index=False)
    return h


if __name__ == '__main__':
    title = ['code', 'name', 'description']
    from app.execption.outer.error import APIException

    _all = []
    result = [[], [], []]
    for module in get_module_from_package(error_code):
        _all += get_classes(module, APIException)
    for _class in set(_all):
        result[0].append(_class.error_code)
        result[1].append(_class.__name__)
        result[2].append(_class.__doc__.strip() if _class.__doc__ else " ")
        print(convert_to_html(result, title))
