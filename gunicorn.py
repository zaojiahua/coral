import os
import shutil

import gevent.monkey

gevent.monkey.patch_all()

if os.path.exists("./app/config/ip.py"):
    os.remove('./app/config/ip.py')
shutil.copyfile('/app/source/ip.py', './app/config/ip.py')

if not os.path.exists("./app/config/secure.py"):
    shutil.copyfile('/app/source/secure.py', './app/config/secure.py')

from server_init import server_init

server_init()

if not os.path.exists('log'):
    os.mkdir('log')

debug = False
loglevel = 'debug'
timeout = 600
bind = '0.0.0.0:8088'
pidfile = 'log/gunicorn.pid'
logfile = 'log/debug.log'
errorlog = 'log/error.log'
accesslog = 'log/access.log'
# from multiprocessing import cpu_count
# workers = cpu_count() * 2 + 1
workers = 1  # 预设2个
worker_class = 'gunicorn.workers.ggevent.GeventWorker'

x_forwarded_for_header = 'X-FORWARDED-FOR'
