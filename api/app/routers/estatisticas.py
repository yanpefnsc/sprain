import asyncpg
from fastapi import APIRouter, Depends
from app.database import get_connection
from app.schemas import ResumoEstatisticas

router = APIRouter(prefix="/api/v1/estatisticas", tags=["Estatisticas e Monitoramento"])

@router.get("/distrito", response_model=ResumoEstatisticas)
async def get_estatisticas_distrito(
    conn: asyncpg.Connection = Depends(get_connection),
):
    sql = '''
        SELECT 
            COUNT(*)::int AS total_trechos,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'critico')::int AS criticos,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'alto')::int AS altos,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'medio')::int AS medios,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'baixo')::int AS baixos,
            COALESCE(ROUND(AVG(ivi_score)::numeric, 2), 0.0)::float AS ivi_medio
        FROM trechos_osm;
    '''
    row = await conn.fetchrow(sql)
    return dict(row)
