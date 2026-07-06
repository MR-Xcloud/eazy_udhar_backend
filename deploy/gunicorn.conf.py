import multiprocessing
import os

bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8099')
workers = int(os.environ.get('GUNICORN_WORKERS', max(2, multiprocessing.cpu_count() * 2 + 1)))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
keepalive = 5
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
wsgi_app = 'easyudhar.wsgi:application'
