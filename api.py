from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import re, os
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
import urllib.parse
import time

load_dotenv()

# Configurações de conexão
server = os.getenv("DB_SERVER")
database = os.getenv("DB_NAME")
username = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
driver = os.getenv("DB_DRIVER")
openai_api_key = os.getenv("OPENAI_API_KEY")
# Inicializar o FastAPI
app = FastAPI(title="TaskPoint SQL API")

# Modelo Pydantic para a entrada da pergunta
class QuestionRequest(BaseModel):
    question: str

# Função para criar conexão com o banco de dados
def create_sql_database_method():
    try:
        print("Estabelecendo conexão com o banco de dados...")
        # Verificar se as variáveis de ambiente estão definidas
        if not all([server, database, username, password, driver, openai_api_key]):
            raise ValueError("Uma ou mais variáveis de ambiente não estão definidas no arquivo .env")

        # Converter para string e garantir que não seja None
        encoded_password = urllib.parse.quote_plus(str(password))
        encoded_driver = urllib.parse.quote_plus(str(driver))
        
        # Construindo URI conforme padrão da SQLAlchemy
        db_uri = f"mssql+pyodbc://{username}:{encoded_password}@{server}/{database}?driver={encoded_driver}&Encrypt=yes&TrustServerCertificate=no&Connection+Timeout=30"
        
        # Criando a conexão
        db = SQLDatabase.from_uri(db_uri)
        
        # Testando a conexão
        print("Testando conexão com consulta simples...")
        result = db.run("SELECT @@VERSION AS version")
        print(f"Conexão bem-sucedida! Versão: {result}")
        return db
    except Exception as e:
        print(f"Erro na conexão: {e}")
        return None

# Função para obter conexão com o banco
def get_working_db_connection():
    db = create_sql_database_method()
    if db:
        return db
    raise Exception("Falha na conexão com o banco de dados.")

# Configurar o assistente SQL
def setup_sql_assistant(db):
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        openai_api_key=openai_api_key
    )

    sql_prompt = PromptTemplate(
        input_variables=["input", "table_info"],
        template="Generate a SQL Server query for the question: {input}. Use the table information: {table_info}. Use square brackets [] for identifiers and avoid backticks. Return only the SQL query inside ```sql ... ```."
    )

    response_prompt = PromptTemplate(
        input_variables=["question", "sql_query", "result"],
        template="Based on the question '{question}', the SQL query '{sql_query}', and the result '{result}', provide a natural, human-friendly response in Portuguese. For example, for a count query, say 'No sistema, atualmente temos X [entidade]'. For a date/time query, say 'A data/hora da última [entidade] foi [valor]'. Avoid technical details and keep the response concise and conversational."
    )

    def extract_content(x):
        return x.content

    input_mapper = RunnablePassthrough.assign(
        input=lambda x: x["input"],
        table_info=lambda x: x["table_info"]
    )
    sql_chain = (
        input_mapper
        .pipe(sql_prompt)
        .pipe(llm)
        .pipe(extract_content)
    )

    response_mapper = RunnablePassthrough.assign(
        question=lambda x: x["question"],
        sql_query=lambda x: x["sql_query"],
        result=lambda x: x["result"]
    )
    response_chain = (
        response_mapper
        .pipe(response_prompt)
        .pipe(llm)
        .pipe(extract_content)
    )

    return sql_chain, response_chain

# Função para extrair consulta SQL
def extract_sql_query(response):
    match = re.search(r'```sql\n(.*?)\n```', response, re.DOTALL)
    return match.group(1).strip() if match else response.strip()

# Conexão global com o banco (inicializada na inicialização da API)
db = get_working_db_connection()
sql_chain, response_chain = setup_sql_assistant(db)

# Endpoint da API
@app.post("/ask")
async def ask_question(request: QuestionRequest):
    try:
        start_time = time.time()
        table_info = db.get_table_info()
        sql_response = sql_chain.invoke({"input": request.question, "table_info": table_info})
        sql_query = extract_sql_query(sql_response)
        result = db.run(sql_query)
        formatted_response = response_chain.invoke({
            "question": request.question,
            "sql_query": sql_query,
            "result": result
        })
        end_time = time.time()
        return {
            "response": formatted_response,
            "sql_query": sql_query,
            "execution_time": f"{end_time - start_time:.2f} seconds"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")

# Endpoint de saúde para verificar se a API está funcionando
@app.get("/health")
async def health_check():
    return {"status": "API is running", "database_connected": db is not None}