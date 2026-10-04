from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import asyncpg
from app.database import get_connection

router = APIRouter(prefix="/api/v1/simulacao", tags=["Simulação de Chuva"])

class SimulacaoRequest(BaseModel):
    milimetros_chuva: float = Field(..., ge=5.0, le=200.0, description="Volume acumulado em mm")

@router.post("/disparar")
async def disparar_simulacao(dados: SimulacaoRequest, conn: asyncpg.Connection = Depends(get_connection)):
    limiar_calculado = float(max(35.0, 85.0 - (dados.milimetros_chuva * 0.6)))
    relato = f"Simulacao hidrologica: precipitacao projetada de {dados.milimetros_chuva} mm"

    query = """
    WITH vias_afetadas AS (
        SELECT id_trecho, CAST(COALESCE(ivi_score, 0) AS float8) AS valor_ivi
        FROM trechos_osm
        WHERE CAST(COALESCE(ivi_score, 0) AS float8) >= $1::float8
    )
    INSERT INTO estado_operacional_trechos (id_trecho, status, severidade, relato_origem, registrado_em)
    SELECT 
        id_trecho,
        CASE 
            WHEN valor_ivi >= 70.0 THEN 'INTRANSITAVEL'
            ELSE 'INTRANSITAVEL_LEVES'
        END,
        CASE 
            WHEN valor_ivi >= 70.0 THEN 'VERMELHO'
            ELSE 'LARANJA'
        END,
        $2,
        NOW()
    FROM vias_afetadas
    ON CONFLICT (id_trecho) DO UPDATE
    SET status = EXCLUDED.status,
        severidade = EXCLUDED.severidade,
        relato_origem = EXCLUDED.relato_origem,
        registrado_em = NOW()
    RETURNING id_trecho;
    """

    rows = await conn.fetch(query, limiar_calculado, relato)

    return {
        "sucesso": True,
        "cenario_mm": dados.milimetros_chuva,
        "limiar_ivi_aplicado": round(limiar_calculado, 2),
        "total_vias_comprometidas": len(rows)
    }
