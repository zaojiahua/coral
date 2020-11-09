import os

from werkzeug._compat import text_type
from werkzeug.exceptions import HTTPException


class LogResponse(HTTPException):
    title = "LOG"

    def __init__(self, description=None, title=None):
        if title:
            self.title = title
        super().__init__(description)

    def get_body(self, environ=None):
        return text_type(
            (
                u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
                u"<title>%(log)s</title>\n"
                u"<h1>%(log)s</h1>\n"
                u"%(description)s\n"
            )
            % {
                "log": self.title,
                "description": self.get_description(environ),
            }
        )


def log_response(param_dict, file):
    try:
        limit = int(param_dict.get("limit"))
        offset = int(param_dict.get("offset"))
    except:
        return "parameter should include limit(Int) and offset(Int)", 400
    if os.path.exists(file):
        return get_part_content(file, offset, limit, param_dict.get("reverse"))
    else:
        return "file not exist", 400


def get_part_content(path, offset, limit,reverse=False):
    global temp_log
    if path in temp_log.keys():
        f = temp_log.get(path)
    elif path not in temp_log.keys() and temp_log is not {}:
        for i in temp_log.values():
            i.close()
        temp_log.clear()
        f = open(path, "rb")
        temp_log[path] = f
    else:
        f = open(path, "rb")
        temp_log[path] = f
    if reverse == True:
        f.seek(int(limit)*20000,2)
    else:
        f.seek(int(offset * 20000), 0)
    ret_string = f.read(int(limit) * 20000)
    if not ret_string or len(ret_string) < 3:
        f.close()
        temp_log.clear()
        return "file read to end", 400
    return ret_string, 200


temp_log = {}
