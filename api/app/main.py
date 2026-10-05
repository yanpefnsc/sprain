from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.database import init_db_pool, close_db_pool
from app.routers import estatisticas, trechos, ocorrencias, rotas, simulacao, relatorios

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(
    title="SPRAIN Geo-Engine API",
    version="1.0.0",
    description="Servicos geoespaciais e calculo de intransitabilidade viaria por alagamento",
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

BASE_DIR = Path(__file__).resolve().parent.parent
static_dir = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import FileResponse
    return FileResponse(str(static_dir / "index.html"))

@app.get("/health", tags=["Infraestrutura"])
async def health_check():
    return {"status": "operacional"}
