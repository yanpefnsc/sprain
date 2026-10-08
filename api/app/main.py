from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.database import init_db_pool, close_db_pool
from app.routers import estatisticas, trechos, ocorrencias, rotas, simulacao, relatorios, monitoramento, logistica

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(
    title="SPRain Geo-Engine B2B API",
    version="2.0.0",
    description="Inteligência Climática e Resiliência Operacional para Logística",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

BASE_DIR = Path(__file__).resolve().parent.parent
static_dir = BASE_DIR / "static"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/health", tags=["Infraestrutura"])
async def health_check():
    return {"status": "operacional", "modulo": "B2B Resilience Engine"}
