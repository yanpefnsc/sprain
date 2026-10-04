from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import asyncpg
from app.database import get_connection

router = APIRouter(prefix="/api/v1/rotas", tags=["Rotas e Navegação"])

class RotaRequest(BaseModel):
    origem_lat: float = Field(..., ge=-90, le=90)
    origem_lon: float = Field(..., ge=-180, le=180)
    destino_lat: float = Field(..., ge=-90, le=90)
    destino_lon: float = Field(..., ge=-180, le=180)

@router.post("/calcular")
async def calcular_rota(dados: RotaRequest, conn: asyncpg.Connection = Depends(get_connection)):
    query = """
    WITH pontos AS (
        SELECT 
            ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 31983) AS pt_origem,
            ST_Transform(ST_SetSRID(ST_MakePoint($3, $4), 4326), 31983) AS pt_destino
    ),
    vias_custo AS (
        SELECT 
            t.id_trecho,
            t.name,
            t.geom,
            ST_Length(t.geom) AS comprimento,
            CASE 
                WHEN e.status = 'INTRANSITAVEL' THEN 999999
                WHEN e.status = 'INTRANSITAVEL_LEVES' THEN ST_Length(t.geom) * 5
                WHEN e.status = 'TRANSITAVEL_ALERTA' THEN ST_Length(t.geom) * 2
                ELSE ST_Length(t.geom)
            END AS custo_efetivo
        FROM trechos_osm t
        LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho
    ),
    via_inicio AS (
        SELECT v.id_trecho, v.geom
        FROM vias_custo v, pontos p
        ORDER BY v.geom <-> p.pt_origem
        LIMIT 1
    ),
    via_fim AS (
        SELECT v.id_trecho, v.geom
        FROM vias_custo v, pontos p
        ORDER BY v.geom <-> p.pt_destino
        LIMIT 1
    )
    SELECT 
        json_build_object(
            'type', 'FeatureCollection',
            'features', json_agg(
                json_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(ST_Transform(v.geom, 4326))::json,
                    'properties', json_build_object(
                        'id_trecho', v.id_trecho,
                        'nome', v.name,
                        'custo', v.custo_efetivo
                    )
                )
            )
        ) AS rota_geojson
    FROM vias_custo v
    WHERE v.id_trecho IN ((SELECT id_trecho FROM via_inicio), (SELECT id_trecho FROM via_fim));
    """
    
    row = await conn.fetchrow(
        query,
        dados.origem_lon,
        dados.origem_lat,
        dados.destino_lon,
        dados.destino_lat
    )

    if not row or not row["rota_geojson"]:
        raise HTTPException(status_code=404, detail="Não foi possível calcular um trajeto viário viável.")

    return row["rota_geojson"]
