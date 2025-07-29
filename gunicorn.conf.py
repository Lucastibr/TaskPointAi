# Configuração do Gunicorn para Azure App Service
import os

# Configurações básicas
bind = "0.0.0.0:8000"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 600
keepalive = 2

# Logs
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Configurações de processo
max_requests = 1000
max_requests_jitter = 100
preload_app = False

# Configurações específicas para Azure
worker_tmp_dir = "/dev/shm"
tmp_upload_dir = None