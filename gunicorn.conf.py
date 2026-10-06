import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
# Omit query strings (which may contain personal data) from access logs.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
# Gunicorn 26 control socket otherwise writes under ~/.gunicorn; container is read-only.
control_socket_disable = True
