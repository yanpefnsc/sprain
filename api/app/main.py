from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.database import close_db_pool, init_db_pool
from app.routers import estatisticas, trechos, ocorrencias

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = BASE_DIR / "static" / "index.html"

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()

app = FastAPI(
    title="SPRAIN Geo-Engine API",
    description="Servicos geoespaciais e calculo de intransitabilidade viaria por alagamento.",
    version="1.0.0",
    lifespan=lifespan,
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

@app.get("/", include_in_schema=False)
async def serve_map():
    return FileResponse(INDEX_HTML)

@app.get("/health", tags=["Infraestrutura"])
async def health_check():
    return {"status": "ok", "service": "sprain-api"}
