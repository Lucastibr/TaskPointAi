from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
from dotenv import load_dotenv
import os
import urllib.parse
import logging
import json
import uuid

from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI

# ============================================
# Configuração básica
# ============================================

load_dotenv()

logger = logging.getLogger("taskpoint-intents-api")
logging.basicConfig(level=logging.INFO)

server = os.getenv("DB_SERVER")
database = os.getenv("DB_NAME")
username = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
driver = os.getenv("DB_DRIVER")
openai_api_key = os.getenv("OPENAI_API_KEY")

if not all([server, database, username, password, driver, openai_api_key]):
    raise RuntimeError("Variáveis de ambiente DB_* ou OPENAI_API_KEY não configuradas.")


def create_sql_database() -> SQLDatabase:
    encoded_password = urllib.parse.quote_plus(str(password))
    encoded_driver = urllib.parse.quote_plus(str(driver))

    db_uri = (
        f"mssql+pyodbc://{username}:{encoded_password}"
        f"@{server}/{database}?driver={encoded_driver}"
        "&TrustServerCertificate=no"
    )
    db = SQLDatabase.from_uri(db_uri)
    logger.info("Testando conexão com o banco...")
    logger.info("Conexão com o banco configurada.")
    return db

db = create_sql_database()

# ============================================
# Modelos de domínio (usuário, intents, etc.)
# ============================================

class UserRole:
    EMPLOYEE = "EMPLOYEE"
    RH_ADMIN = "RH_ADMIN"
    MANAGER = "MANAGER"


class AuthenticatedUser(BaseModel):
    pessoa_id: Optional[str]  # GUID de Pessoa.Id
    name: str
    role: str  # usar valores de UserRole


class QuestionRequest(BaseModel):
    question: str = Field(..., description="Pergunta em linguagem natural.")
    user_id: Optional[str] = Field(
        default=None,
        description="GUID de Pessoa.Id para testes (pessoa logada)."
    )
    role: Optional[str] = Field(
        default=UserRole.EMPLOYEE,
        description="EMPLOYEE | RH_ADMIN | MANAGER (para testes)."
    )
    name: Optional[str] = Field(
        default="Usuário Teste",
        description="Nome do usuário (só para contexto de prompt)."
    )


class Period(BaseModel):
    type: Optional[Literal["DAY", "RANGE", "MONTH"]] = None
    from_date: Optional[str] = None  # yyyy-MM-dd
    to_date: Optional[str] = None    # yyyy-MM-dd


class IntentDto(BaseModel):
    intent: Literal[
        "GET_EMPLOYEE_BANK_HOURS",
        "GET_NEXT_VACATION_PERIOD",
        "GET_ABSENT_EMPLOYEES",
        "UNKNOWN",
    ]
    employee_scope: Optional[Literal["SELF", "ONE", "ALL"]] = None
    target_employee_name: Optional[str] = None
    date: Optional[str] = None          # yyyy-MM-dd
    period: Optional[Period] = None


class ChatResponse(BaseModel):
    intent: str
    params: dict
    raw_result: Optional[object]
    natural_response: str


def validate_guid(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail="user_id não é um GUID válido.")


# ============================================
# LLM – classificação de intents e resposta natural
# ============================================

llm_intent = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=openai_api_key,
)

llm_natural = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=openai_api_key,
)

INTENT_SYSTEM_PROMPT = """
Você é um classificador de intenções especializado no sistema de ponto eletrônico.

SEMPRE responda APENAS o JSON do intent.

Regras:
- NÃO gere SQL.
- NÃO explique nada fora do JSON.
- Saída DEVE ser sempre JSON válido.

FORMATO:
{
  "intent": "...",
  "employee_scope": "SELF" | "ONE" | "ALL" | null,
  "target_employee_name": "string ou null",
  "date": "yyyy-MM-dd ou null",
  "period": {
    "type": "DAY" | "RANGE" | "MONTH" | null,
    "from_date": "yyyy-MM-dd ou null",
    "to_date": "yyyy-MM-dd ou null"
  }
}

INTENTS SUPORTADOS:

1) GET_EMPLOYEE_BANK_HOURS
Usar quando o usuário perguntar sobre:
- "horas que eu tenho"
- "horas acumuladas"
- "banco de horas"
- "saldo de horas"
- "quantas horas eu tenho na casa"  <-- expressão típica do sistema
- "quanto eu tenho de banco"

SEMPRE que o usuário usar "eu", "meu", "minhas", "para mim":
employee_scope = "SELF".

2) GET_NEXT_VACATION_PERIOD
Perguntas sobre próxima férias:
- "quando tiro férias?"
- "quando são minhas férias?"
- "qual meu próximo período de férias?"

3) GET_ABSENT_EMPLOYEES
Perguntas sobre faltas:
- "quem faltou hoje?"
- "quais funcionários faltaram?"
- "quem não veio?"

SE A PERGUNTA FOR DUVIDOSA:
- PREFIRA CLASSIFICAR como um desses intents ao invés de UNKNOWN.
- Só use UNKNOWN se realmente não for RH/ponto eletrônico.

"""

def classify_intent(question: str, user: AuthenticatedUser) -> IntentDto:
    user_context = f"Usuário: {user.name}, pessoa_id={user.pessoa_id}, role={user.role}"
    prompt = (
        INTENT_SYSTEM_PROMPT
        + "\n\n"
        + f"Contexto de usuário: {user_context}\n"
        + f"Pergunta: \"{question}\"\n"
        + "Responda apenas com o JSON do intent."
    )
    msg = llm_intent.invoke(prompt)
    content = msg.content.strip()
    logger.info(f"Intent raw LLM: {content}")

    try:
        data = json.loads(content)
        intent = IntentDto(**data)
    except Exception as e:
        logger.exception(f"Erro ao parsear Intent JSON: {e}")
        intent = IntentDto(intent="UNKNOWN")
    return intent


# ============================================
# Autorização por intent
# ============================================

def ensure_authorization(user: AuthenticatedUser, intent: IntentDto):
    if intent.intent == "GET_EMPLOYEE_BANK_HOURS":
        if user.role == UserRole.EMPLOYEE and intent.employee_scope != "SELF":
            raise HTTPException(
                status_code=403,
                detail="Você só pode consultar o seu próprio banco de horas.",
            )
        return

    if intent.intent == "GET_NEXT_VACATION_PERIOD":
        if user.role == UserRole.EMPLOYEE and intent.employee_scope != "SELF":
            raise HTTPException(
                status_code=403,
                detail="Você só pode consultar as suas próprias férias.",
            )
        return

    if intent.intent == "GET_ABSENT_EMPLOYEES":
        if user.role not in (UserRole.RH_ADMIN, UserRole.MANAGER):
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para consultar faltas de funcionários.",
            )
        return

    if intent.intent == "UNKNOWN":
        raise HTTPException(
            status_code=400,
            detail="Não entendi sua pergunta ou ela ainda não é suportada.",
        )


# ============================================
# Handlers de intents – SQL fixo no seu schema
# ============================================

def lookup_pessoa_id_by_name(nome: str) -> str:
    # Isso é teste/MVP, então vai direto por nome exato.
    sql = f"""
        SELECT TOP 1 [Id]
        FROM [dbo].[Pessoa]
        WHERE [Nome] = '{nome.replace("'", "''")}'
    """
    result = db.run(sql)
    if not result:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada.")
    return str(result[0]["Id"])


def handle_get_employee_bank_hours(intent: IntentDto, user: AuthenticatedUser):
    if intent.employee_scope == "SELF":
        if not user.pessoa_id:
            raise HTTPException(status_code=400, detail="user_id (pessoa_id) é obrigatório para SELF.")
        pessoa_id = user.pessoa_id
    elif intent.employee_scope == "ONE" and intent.target_employee_name:
        pessoa_id = lookup_pessoa_id_by_name(intent.target_employee_name)
    else:
        raise HTTPException(
            status_code=400,
            detail="Escopo de funcionário inválido para banco de horas.",
        )

    validate_guid(pessoa_id)

    # Exemplo: histórico de registros + saldo atual
    sql = f"""
        SELECT
            b.[PessoaId],
            p.[Nome],
            b.[Saldo],
            b.[DataCriacao],
            b.[DataAtualizacao],
            rb.[DataRegistro],
            rb.[TipoRegistro],
            rb.[QuantidadeHoras],
            rb.[Descricao]
        FROM [dbo].[BancoHoras] b
        LEFT JOIN [dbo].[RegistroBancoHoras] rb
            ON rb.[BancoHorasId] = b.[Id]
        JOIN [dbo].[Pessoa] p
            ON p.[Id] = b.[PessoaId]
        WHERE b.[PessoaId] = CONVERT(uniqueidentifier, '{pessoa_id}')
        ORDER BY rb.[DataRegistro] DESC, b.[DataAtualizacao] DESC, b.[DataCriacao] DESC;
    """
    result = db.run(sql)
    return result


def handle_get_next_vacation_period(intent: IntentDto, user: AuthenticatedUser):
    if intent.employee_scope == "SELF":
        if not user.pessoa_id:
            raise HTTPException(status_code=400, detail="user_id (pessoa_id) é obrigatório para SELF.")
        pessoa_id = user.pessoa_id
    elif intent.employee_scope == "ONE" and intent.target_employee_name:
        pessoa_id = lookup_pessoa_id_by_name(intent.target_employee_name)
    else:
        raise HTTPException(
            status_code=400,
            detail="Escopo de funcionário inválido para férias.",
        )

    validate_guid(pessoa_id)

    # Ferias: próximo período futuro
    # Ajuste Status conforme sua convenção (apenas aprovadas, etc.)
    sql = f"""
        SELECT TOP 1
            f.[PessoaId],
            p.[Nome],
            f.[DataInicio],
            f.[DataFim],
            f.[DiasConcedidos],
            f.[Status],
            f.[FoiFracionada],
            f.[NumeroParcelas],
            f.[Observacoes]
        FROM [dbo].[Ferias] f
        JOIN [dbo].[Pessoa] p ON p.[Id] = f.[PessoaId]
        WHERE f.[PessoaId] = CONVERT(uniqueidentifier, '{pessoa_id}')
          AND CONVERT(date, f.[DataInicio]) >= CONVERT(date, GETDATE())
        ORDER BY f.[DataInicio] ASC;
    """
    result = db.run(sql)
    return result


def handle_get_absent_employees(intent: IntentDto, user: AuthenticatedUser):
    # RH / gestor – lista quem não teve registro de horas na data
    if intent.date:
        date_expr = intent.date
        date_sql = f"CONVERT(date, '{date_expr}')"
    else:
        date_sql = "CONVERT(date, GETDATE())"

    sql = f"""
        SELECT
            p.[Id]          AS PessoaId,
            p.[Nome],
            p.[Matricula],
            vt.[DataAdmissao],
            vt.[DataDesligamento]
        FROM [dbo].[Pessoa] p
        JOIN [dbo].[VinculoTrabalho] vt
            ON vt.[PessoaId] = p.[Id]
        WHERE
            (vt.[Ativo] = 1 OR vt.[Ativo] IS NULL)
            AND (vt.[DataDesligamento] IS NULL OR CONVERT(date, vt.[DataDesligamento]) >= {date_sql})
            AND NOT EXISTS (
                SELECT 1
                FROM [dbo].[SomaHorasPeriodo] shp
                WHERE shp.[PessoaId] = p.[Id]
                  AND CONVERT(date, shp.[DataHoraRegistro]) = {date_sql}
            );
    """
    result = db.run(sql)
    return result


def execute_intent(intent: IntentDto, user: AuthenticatedUser):
    ensure_authorization(user, intent)

    if intent.intent == "GET_EMPLOYEE_BANK_HOURS":
        return handle_get_employee_bank_hours(intent, user)

    if intent.intent == "GET_NEXT_VACATION_PERIOD":
        return handle_get_next_vacation_period(intent, user)

    if intent.intent == "GET_ABSENT_EMPLOYEES":
        return handle_get_absent_employees(intent, user)

    raise HTTPException(status_code=400, detail="Intent não suportado.")


# ============================================
# Resposta natural em PT-BR
# ============================================

def build_natural_response(question: str, intent: IntentDto, raw_result) -> str:
    prompt = f"""
Pergunta do usuário: "{question}"

Intent identificada: {intent.intent}
Intent JSON: {intent.json()}
Resultado bruto da consulta ao banco (JSON): {json.dumps(raw_result, default=str)}

Gere uma resposta curta, clara e em português, explicando o resultado de forma amigável.
Não mostre SQL. Evite termos técnicos.
Se não houver dados (lista vazia ou null), explique de forma simples.
"""
    msg = llm_natural.invoke(prompt)
    return msg.content.strip()


# ============================================
# FastAPI
# ============================================

app = FastAPI(title="TaskPoint - Chat com Intents")

@app.post("/chat", response_model=ChatResponse)
async def chat(request: QuestionRequest):
    # Monta "usuário autenticado" a partir do body (MVP de teste)
    pessoa_id = validate_guid(request.user_id) if request.user_id else None

    user = AuthenticatedUser(
        pessoa_id=pessoa_id,
        name=request.name or "Usuário Teste",
        role=request.role or UserRole.EMPLOYEE,
    )

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pergunta vazia.")

    # 1) Classificar intent
    intent = classify_intent(question, user)
    logger.info(f"Intent final: {intent.json()}")

    # 2) Executar intent (SQL fixo)
    raw_result = execute_intent(intent, user)

    # 3) Resposta amigável
    natural_response = build_natural_response(question, intent, raw_result)

    return ChatResponse(
        intent=intent.intent,
        params=json.loads(intent.json()),
        raw_result=raw_result,
        natural_response=natural_response,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "database": database}
