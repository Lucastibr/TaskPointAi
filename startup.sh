#!/bin/bash
echo "Instalando dependências..."
pip install -r /home/site/wwwroot/requirements.txt

echo "Configurando variáveis de ambiente..."
export PYTHONPATH="/home/site/wwwroot:$PYTHONPATH"

echo "Iniciando Gunicorn com configuração personalizada..."
exec gunicorn --config gunicorn.conf.py api:app
