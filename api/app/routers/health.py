import time
import asyncpg
from fastapi import APIRouter, HTTPException, status
from app.config import settings
import app.database as db

router = APIRouter(prefix="/api/v1/health", tags=["health"])

@router.get("/liveness", status_code=status.HTTP_200_OK)
async def check_liveness():
    return {
        "status": "UP",
        "timestamp": time.time(),
        "servico": "sprain_api"
    }

@router.get("/readiness", status_code=status.HTTP_200_OK)
async def check_readiness():
    inicio = time.perf_counter()
    try:
        if getattr(db, "db_pool", None) is not None:
            async with db.db_pool.acquire() as conn:
                total_trechos = await conn.fetchval("SELECT COUNT(*) FROM trechos_osm")
        else:
            conn = await asyncpg.connect(settings.database_url, timeout=5.0)
            try:
                total_trechos = await conn.fetchval("SELECT COUNT(*) FROM trechos_osm")
            finally:
                await conn.close()

        latencia_db_ms = round((time.perf_counter() - inicio) * 1000.0, 2)
        return {
            "status": "READY",
            "banco": "sprain_db",
            "postgis": "OPERACIONAL",
            "total_trechos_osm": total_trechos,
            "latencia_db_ms": latencia_db_ms
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha de conexao com a malha PostGIS: {str(e)}"
        )
