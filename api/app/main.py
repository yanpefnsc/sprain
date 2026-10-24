import os
import sys
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.manutencao import carregar_janela
from app.versao import API_VERSION, informacao_versao
from app.services.demonstracao import validar_configuracao as validar_demonstracao, habilitada as demonstracao_habilitada
from app.seguranca import validar_configuracao_producao
from app.services.security_headers import SecurityHeadersMiddleware
from app.services.observabilidade import ObservabilidadeMiddleware
from app.database import init_db_pool, close_db_pool
from app.services.webhook_dispatcher import WebhookDispatcher
from app.services.infraestrutura_viaria import garantir_schema as garantir_infraestrutura
from app.services.dados_publicos import garantir_schema as garantir_dados_publicos
from app.services.esquema_operacional import garantir_schema as garantir_esquema_operacional
from app.services.auditoria import garantir_schema as garantir_auditoria
from app.services.painel import garantir_schema as garantir_painel
from app.routers import painel
from app.routers import acesso_painel
from app.routers import gestao_usuarios
from app.routers import administracao_painel
from app.routers import relatorios_painel
from app.routers import operacional_interno
from app.routers import resultados_viagem
from app.services.administracao_painel import garantir_schema as garantir_administracao
from app.services.acesso_painel import garantir_schema as garantir_acesso
from app.services.resultados_viagem import garantir_schema as garantir_resultados_viagem
from app.services.planos_empresa import garantir_schema as garantir_planos_empresa
from app.routers import infraestrutura, malha, dados_publicos, transito, indicadores, demonstracao, feedback_alertas, operacoes_cliente
from app.routers import (
    estatisticas,
    trechos,
    ocorrencias,
    rotas,
    simulacao,
    relatorios,
    monitoramento,
    logistica,
    health
)

async def agendador_telemetria_corredor():
    while True:
        try:
            await asyncio.sleep(1800)
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "/app/scripts/sincronizar_clima_corredor.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        except asyncio.CancelledError:
            break
        except Exception:
            pass


def coleta_corredor_automatica_habilitada() -> bool:
    """A coleta gratuita do corredor não deve iniciar no piloto comercial."""
    return settings.ambiente_atual != "production" and not demonstracao_habilitada()

@asynccontextmanager
async def lifespan(app: FastAPI):
    carregar_janela()
    identificacao = informacao_versao()
    logging.getLogger("uvicorn.error").info(
        "SPRain iniciando versao=%s revisao=%s",
        identificacao["versao_api"], identificacao["revisao"] or "nao_informada",
    )
    validar_configuracao_producao()
    validar_demonstracao()
    await init_db_pool()
    await WebhookDispatcher.garantir_schema()
    await garantir_infraestrutura()
    await garantir_dados_publicos()
    await garantir_esquema_operacional()
    await garantir_auditoria()
    await garantir_painel()
    await garantir_resultados_viagem()
    await garantir_acesso()
    await garantir_administracao()
    await garantir_planos_empresa()
    task_clima = (asyncio.create_task(agendador_telemetria_corredor())
                  if coleta_corredor_automatica_habilitada() else None)
    try:
        yield
    finally:
        if task_clima:
            task_clima.cancel()
            try:
                await task_clima
            except asyncio.CancelledError:
                pass
        await close_db_pool()

tags_metadata = [
    {
        "name": "Logistica & Roteamento Resiliente",
        "description": "Simulacao de impacto viario por alagamentos, previsao D-1 e roteamento de frotas sobre a malha PostGIS."
    },
    {
        "name": "Relatorios & Auditoria Executiva",
        "description": "Exportacao tabular CSV em streaming e sumarios consolidados de KPIs de resiliencia e prejuizo evitado."
    },
    {
        "name": "Webhooks Corporativos",
        "description": "Assinatura HMAC-SHA256 e despacho assincrono de eventos criticos de rota e alagamento para ERPs e TMSs."
    },
    {
        "name": "Observabilidade & Quotas",
        "description": "Telemetria de performance em tempo real, monitoramento de latencia e governanca de rate limit."
    },
    {
        "name": "Healthchecks & Infraestrutura",
        "description": "Sondas de vivacidade (liveness) e prontidao (readiness) com validacao de conexao ativa na malha viaria."
    }
]

app = FastAPI(
    title="SPRain B2B - Climate Resilience & Logistics Intelligence API",
    description="Apoio a decisao logistica com vulnerabilidade viaria, cenarios climaticos, rotas alternativas e custos com fontes e limitacoes explicitas.",
    version=API_VERSION,
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(ObservabilidadeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origens_cors,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trechos.router)
app.include_router(estatisticas.router)
app.include_router(ocorrencias.router)
app.include_router(rotas.router)
app.include_router(simulacao.router)
app.include_router(relatorios.router)
app.include_router(monitoramento.router)
app.include_router(logistica.router)
app.include_router(health.router)
app.include_router(infraestrutura.router)
app.include_router(malha.router)
app.include_router(dados_publicos.router)
app.include_router(transito.router)
app.include_router(indicadores.router)
app.include_router(demonstracao.router)
app.include_router(feedback_alertas.router)
app.include_router(operacoes_cliente.router)
app.include_router(painel.router)
app.include_router(acesso_painel.router)
app.include_router(gestao_usuarios.router)
app.include_router(administracao_painel.router)
app.include_router(relatorios_painel.router)
app.include_router(operacional_interno.router)
app.include_router(resultados_viagem.router)

BASE_DIR = Path(__file__).resolve().parent.parent
static_dir = BASE_DIR / "static"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/health", tags=["Healthchecks & Infraestrutura"])
async def health_check():
    return {"status": "operacional", "modulo": "B2B Resilience Engine"}

@app.get('/',include_in_schema=False)
async def pagina_inicial():
    return RedirectResponse('/static/b2b.html')

from app.documentacao import instalar as instalar_documentacao
instalar_documentacao(app)
