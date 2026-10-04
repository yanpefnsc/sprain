from fastapi import APIRouter, Depends
import asyncpg
from app.database import get_connection

router = APIRouter(prefix="/api/v1/relatorios", tags=["Relatórios Executivos"])

@router.get("/boletim-situacao")
async def gerar_boletim_situacao(conn: asyncpg.Connection = Depends(get_connection)):
    query_resumo = """
    SELECT 
        COUNT(*) AS total_bloqueadas,
        COUNT(*) FILTER (WHERE severidade = 'VERMELHO') AS total_vermelho,
        COUNT(*) FILTER (WHERE severidade = 'LARANJA') AS total_laranja,
        COUNT(*) FILTER (WHERE severidade = 'AMARELO') AS total_amarelo
    FROM estado_operacional_trechos
    WHERE status != 'TRANSITAVEL';
    """
    
    query_vias = """
    SELECT 
        e.id_trecho,
        t.name AS nome_via,
        e.status,
        e.severidade,
        e.relato_origem,
        TO_CHAR(e.registrado_em, 'DD/MM/YYYY HH24:MI:SS') AS data_registro
    FROM estado_operacional_trechos e
    JOIN trechos_osm t ON t.id_trecho = e.id_trecho
    WHERE e.status != 'TRANSITAVEL'
    ORDER BY 
        CASE e.severidade 
            WHEN 'VERMELHO' THEN 1 
            WHEN 'LARANJA' THEN 2 
            WHEN 'AMARELO' THEN 3 
            ELSE 4 
        END,
        e.registrado_em DESC;
    """

    resumo = await conn.fetchrow(query_resumo)
    vias = await conn.fetch(query_vias)

    return {
        "orgao": "DEFESA CIVIL - SALA DE SITUAÇÃO SPRAIN",
        "distrito": "Itaquera",
        "sumario_executivo": {
            "total_vias_comprometidas": resumo["total_bloqueadas"] or 0,
            "bloqueio_total_vermelho": resumo["total_vermelho"] or 0,
            "risco_alto_laranja": resumo["total_laranja"] or 0,
            "atencao_amarelo": resumo["total_amarelo"] or 0
        },
        "detalhamento_vias": [dict(v) for v in vias]
    }
