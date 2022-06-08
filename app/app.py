import time

import requests
from flask import Flask
from flask_cors import CORS

from app.config.setting import EXPOSE_HEADERS, SERVER_INIT
from app.v1.Cuttle.basic.url import basic
from app.v1.Cuttle.boxSvc.url import resource
from app.v1.Cuttle.macPane.init import pane_init
from app.v1.Cuttle.macPane.url import pane
from app.v1.Cuttle.paneDoor.url import door
from app.v1.djob.views import djob_router
from app.v1.eblock.url import eblock
from app.v1.log_view import log
from app.v1.stew.init import calculate_matrix
from app.v1.tboard.views import tborad_router
from app.config.url import bounced_words_url
from extensions import ma
from app.v1.eblock.model.bounced_words import BouncedWords
from app.libs.http_client import _parse_url


def register_blueprints(app: Flask):
    app.register_blueprint(tborad_router, url_prefix='/tboard')
    app.register_blueprint(djob_router, url_prefix='/djob')
    app.register_blueprint(eblock, url_prefix='/eblock')
    app.register_blueprint(log, url_prefix='/log')
    app.register_blueprint(resource, url_prefix='/resource')
    app.register_blueprint(door, url_prefix='/door')
    app.register_blueprint(pane, url_prefix='/pane')
    app.register_blueprint(basic, url_prefix='/basic')


def register_extensions(app):
    ma.init_app(app)


def load_setting(app):
    app.config.from_object('app.config.setting')
    app.config.from_object('app.config.secure')

    # 获取 t-guard 干扰词的配置
    bounced_words = requests.get(_parse_url(bounced_words_url)).json()
    print('获取到干扰词是：', bounced_words, '*' * 10)
    all_words = {}
    for word in bounced_words:
        all_words[word['id']] = word['name']
    BouncedWords(words=all_words)


def server_init_inside():
    calculate_matrix()
    time.sleep(5)
    pane_init()  # pane_init must after tboard_init
    # hand_init()


def create_app():
    if SERVER_INIT:
        from server_init import server_init
        server_init()
    # __name__ 指向app.app,因此应用程序更目录为 app 目录 而非更上层的MachExec
    app = Flask(__name__)

    CORS(app, expose_headers=[EXPOSE_HEADERS])

    load_setting(app)

    register_blueprints(app)

    register_extensions(app)

    # logger_init()

    server_init_inside()

    # 主要用来debug 不涉及到业务逻辑
    # t = threading.Thread(target=device_manager_loop)
    # t.start()

    return app


app = create_app()
