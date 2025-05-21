#!/bin/bash
echo "Instalando dependências..."
pip install -r /home/site/wwwroot/requirements.txt

echo "Iniciando Gunicorn com UvicornWorker..."
exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker api:app
