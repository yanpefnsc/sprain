from app.services.security_headers import SecurityHeadersMiddleware
from app.services.observabilidade import ObservabilidadeMiddleware
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.database import init_db_pool, close_db_pool
from app.routers import estatisticas, trechos, ocorrencias, rotas, simulacao, relatorios, monitoramento, logistica, health

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
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
    description="Plataforma corporativa de inteligencia climatica, predicao de intransitabilidade urbana e roteamento dinamico de frotas.",
    version="1.1.0",
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
    allow_origins=["*"],
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

BASE_DIR = Path(__file__).resolve().parent.parent
static_dir = BASE_DIR / "static"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/health", tags=["Healthchecks & Infraestrutura"])
async def health_check():
    return {"status": "operacional", "modulo": "B2B Resilience Engine"}