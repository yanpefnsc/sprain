import asyncpg
from fastapi import APIRouter, Depends
from app.database import get_connection
from app.schemas import ResumoEstatisticas

router = APIRouter(prefix="/api/v1/estatisticas", tags=["Estatisticas e Monitoramento"])


@router.get("/distrito", response_model=ResumoEstatisticas)
async def get_estatisticas_distrito(conn: asyncpg.Connection = Depends(get_connection)):
    sql = """
        SELECT
            COUNT(*)::int AS total_trechos,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'critico')::int AS criticos,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'alto')::int AS altos,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'medio')::int AS medios,
            COUNT(*) FILTER (WHERE LOWER(classe_risco) = 'baixo')::int AS baixos,
            COALESCE(ROUND(AVG(ivi_score)::numeric, 2), 0.0)::float AS ivi_medio,
            (SELECT COUNT(*) FROM estado_operacional_trechos
             WHERE status IN ('INTRANSITAVEL', 'INTRANSITAVEL_LEVES'))::int AS trechos_interditados
        FROM trechos_osm;
    """
    row = await conn.fetchrow(sql)
    return dict(row)


@router.get("/historico-temporal")
async def obter_historico_temporal(conn: asyncpg.Connection = Depends(get_connection)):
    niveis = await conn.fetch("""
        SELECT COALESCE(severidade, 'NORMAL') AS nivel, COUNT(*) AS total
        FROM estado_operacional_trechos
        WHERE status != 'TRANSITAVEL'
        GROUP BY 1;
    """)

    horas = await conn.fetch("""
        SELECT TO_CHAR(registrado_em, 'HH24:00') AS faixa_hora, COUNT(*) AS qtd
        FROM estado_operacional_trechos
        WHERE status != 'TRANSITAVEL'
        GROUP BY 1
        ORDER BY 1;
    """)

    return {
        "niveis": {r["nivel"]: r["total"] for r in niveis},
        "temporal": [{"hora": r["faixa_hora"], "total": r["qtd"]} for r in horas]
    }