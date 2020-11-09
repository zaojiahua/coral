from flask import request, json
from werkzeug.exceptions import HTTPException


class APIException(HTTPException):
    code = 500
    description = 'sorry, we made a mistake (*￣︶￣)!'
    error_code = 999

    def __init__(self, description=None, code=None, error_code=None,
                 headers=None):
        if code:
            self.code = code
        if error_code:
            self.error_code = error_code
        if description:
            self.description = description
        # 父类需要传递 description,response   response为空flask 会自动获取
        super(APIException, self).__init__(description)

    def get_body(self, environ=None):
        body = dict(
            description=self.description,
            error_code=self.error_code,
            request=request.method + ' ' + self.get_url_no_param()
        )
        text = json.dumps(body)
        return text

    def get_headers(self, environ=None):
        """Get a list of headers."""
        return [('Content-Type', 'application/json')]

    @staticmethod
    def get_url_no_param():
        full_path = str(request.full_path)
        main_path = full_path.split('?')
        return main_path[0]
