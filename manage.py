import logging
import os

from werkzeug.exceptions import HTTPException

from app.app import app
from app.config.setting import TOTAL_LOG_NAME, LOG_DIR, BASE_DIR
from app.execption.outer.error import APIException
from app.execption.outer.error_code.total import ServerError, RecvHttpException
from app.libs.logresponse import LogResponse

logger = logging.getLogger(TOTAL_LOG_NAME)


# https://www.cnblogs.com/huchong/p/9205651.html
@app.errorhandler(Exception)
def global_error(error):
    if isinstance(error, APIException):
        logger.exception(f"APIException:{error}")
        logger.error(f"APIException:{error}")
        return error

    if isinstance(error, LogResponse):
        return error

    if isinstance(error, HTTPException):
        logger.exception(f"HTTPException:{error}")
        logger.critical(f"HTTPException:{error}")
        return RecvHttpException(description=error.description, code=error.code)
    else:
        logger.exception(f"unexpectedly Execption:{error}")
        logger.critical(f"unexpectedly Execption:{error}")
        if not app.config['DEBUG']:
            return ServerError()
        else:
            raise error


@app.route('/logger/<string:path>/<string:file>/')
def log(path, file):
    file = os.path.join(LOG_DIR, path, file)
    content = ""
    with open(file, 'r') as f:
        content += f.read()

    return LogResponse(description=content)


@app.route('/doc/')
def doc():
    from app.execption.outer.error import APIException
    from app.execption.outer import error_code
    from app.libs.extension.tools import convert_to_html, get_module_from_package
    import json
    from collections import namedtuple
    SpecialException = namedtuple("SpecialException", ["error_code", "description"])

    title = ['code', 'name', 'description']

    def special_case():
        special_error_file_path = os.path.join(BASE_DIR, "app", "execption", "outer", "error_code",
                                               "special_error.json")
        with open(special_error_file_path, "r") as json_file:
            special_msg_list = json.load(json_file)
        return [
            SpecialException(error_code=special_msg["error_code"], description=special_msg["description"])
            for special_msg in special_msg_list
        ]

    _all = []
    _all += special_case()
    result = [[], [], []]
    for module in get_module_from_package(error_code):
        from app.libs.extension.tools import get_classes
        _all += get_classes(module, APIException)
    for _class in sorted(set(_all), key=lambda obj: obj.error_code):
        result[0].append(_class.error_code)
        result[1].append(_class.__name__ if hasattr(_class, "__name__") else "")
        result[2].append(
            _class.__doc__.strip()
            if not isinstance(_class, SpecialException) and hasattr(_class, "__doc__") and _class.__doc__
            else _class.description
        )
    return convert_to_html(result, title)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
