# Guia de Deploy no Azure App Service

## Problemas Identificados e Soluções Implementadas

### 1. **Versões das Dependências**
- **Problema**: Versões não especificadas podem causar incompatibilidades
- **Solução**: Versões fixas no `requirements.txt`

### 2. **Configuração do Gunicorn**
- **Problema**: Configuração inadequada para Azure App Service
- **Solução**: Arquivo `gunicorn.conf.py` com configurações otimizadas

### 3. **Inicialização da Aplicação**
- **Problema**: Conexões inicializadas no momento da importação podem falhar
- **Solução**: Inicialização lazy das conexões com o banco

### 4. **Variáveis de Ambiente**
- **Problema**: Variáveis não configuradas no Azure
- **Solução**: Endpoint `/health` para verificar configurações

## Configurações Necessárias no Azure App Service

### 1. **Variáveis de Ambiente (Application Settings)**
Configure as seguintes variáveis no portal do Azure:

```
DB_SERVER=seu-servidor.database.windows.net
DB_NAME=nome-do-banco
DB_USER=usuario
DB_PASSWORD=senha
DB_DRIVER=ODBC Driver 18 for SQL Server
OPENAI_API_KEY=sua-chave-openai
```

### 2. **Configurações Gerais**
- **Stack**: Python 3.9 ou superior
- **Startup Command**: `bash startup.sh`
- **Always On**: Habilitado (recomendado)

### 3. **Configurações de Rede**
- Certifique-se de que o Azure App Service pode acessar o SQL Server
- Configure as regras de firewall do SQL Server para permitir serviços do Azure

## Como Testar o Deploy

### 1. **Verificar se a API está funcionando**
```
GET https://seu-app.azurewebsites.net/
```
Deve retornar: `{"message": "TaskPoint SQL API está funcionando!", "status": "online"}`

### 2. **Verificar saúde da aplicação**
```
GET https://seu-app.azurewebsites.net/health
```
Deve mostrar o status da conexão com o banco e variáveis de ambiente.

### 3. **Testar funcionalidade principal**
```
POST https://seu-app.azurewebsites.net/ask
Content-Type: application/json

{
  "question": "Quantos registros temos na tabela?"
}
```

## Logs e Debugging

### 1. **Visualizar Logs**
- No portal do Azure: App Service > Log stream
- Ou use: `az webapp log tail --name seu-app --resource-group seu-grupo`

### 2. **Logs Importantes**
- Logs de inicialização do Gunicorn
- Logs de conexão com o banco de dados
- Logs de erro da aplicação

## Troubleshooting Comum

### 1. **Erro de Conexão com Banco**
- Verificar variáveis de ambiente
- Verificar regras de firewall do SQL Server
- Verificar string de conexão

### 2. **Erro de Importação**
- Verificar se todas as dependências estão instaladas
- Verificar logs de build no GitHub Actions

### 3. **Timeout na Inicialização**
- Aumentar timeout no `gunicorn.conf.py`
- Verificar se o banco está acessível

## Próximos Passos

1. Configure as variáveis de ambiente no Azure
2. Faça push das alterações para o repositório
3. Aguarde o deploy automático via GitHub Actions
4. Teste os endpoints conforme descrito acima
5. Monitore os logs para identificar possíveis problemas