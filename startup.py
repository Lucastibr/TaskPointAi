#!/usr/bin/env python3
import os
import sys
import subprocess

# Adicionar o diretório atual ao Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    try:
        # Instalar dependências se necessário
        print("Verificando dependências...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        
        # Importar e executar a aplicação
        print("Iniciando aplicação...")
        import uvicorn
        from api import app
        
        # Configurar porta do Azure
        port = int(os.environ.get("PORT", 8000))
        
        # Executar aplicação
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True
        )
        
    except Exception as e:
        print(f"Erro ao iniciar aplicação: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()