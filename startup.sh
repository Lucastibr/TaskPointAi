#!/bin/bash
echo "Instalando ODBC Driver 17 para SQL Server..."
apt-get update
apt-get install -y unixodbc-dev
ACCEPT_EULA=Y apt-get install msodbcsql17

echo "Instalando dependências..."
pip install -r requirements.txt

echo "Iniciando Gunicorn com UvicornWorker..."
exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker api:app