from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import json
import asyncpg
from app.database import get_connection

router = APIRouter(prefix="/api/v1/rotas", tags=["Rotas e Navegação"])

# Quanto maior o peso, mais a rota foge dessas vias, mesmo que o desvio seja longo.
# INTRANSITAVEL continua bloqueada (custo -1).
PESO_ALERTA = 10
PESO_LEVES = 100

CUSTO_SQL = f"""CASE
    WHEN e.status = ''INTRANSITAVEL'' THEN -1
    WHEN e.status = ''INTRANSITAVEL_LEVES'' THEN ST_Length(t.geom) * {PESO_LEVES}
    WHEN e.status = ''TRANSITAVEL_ALERTA'' THEN ST_Length(t.geom) * {PESO_ALERTA}
    ELSE ST_Length(t.geom)
END"""


class RotaRequest(BaseModel):
    origem_lat: float = Field(..., ge=-90, le=90)
    origem_lon: float = Field(..., ge=-180, le=180)
    destino_lat: float = Field(..., ge=-90, le=90)
    destino_lon: float = Field(..., ge=-180, le=180)


@router.post("/calcular")
async def calcular_rota(dados: RotaRequest, conn: asyncpg.Connection = Depends(get_connection)):
    query = f"""
    WITH pontos AS (
        SELECT
            ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 31983) AS pt_origem,
            ST_Transform(ST_SetSRID(ST_MakePoint($3, $4), 4326), 31983) AS pt_destino
    ),
    vertices_proximos AS (
        SELECT
            (SELECT v.id FROM trechos_osm_vertices_pgr v, pontos p ORDER BY v.the_geom <-> p.pt_origem LIMIT 1) AS v_inicio,
            (SELECT v.id FROM trechos_osm_vertices_pgr v, pontos p ORDER BY v.the_geom <-> p.pt_destino LIMIT 1) AS v_fim
    ),
    rota_dijkstra AS (
        SELECT d.seq, d.node, d.edge, d.cost
        FROM vertices_proximos vp,
        LATERAL pgr_dijkstra(
            'SELECT
                t.id_trecho AS id,
                t.source::bigint,
                t.target::bigint,
                {CUSTO_SQL} AS cost,
                {CUSTO_SQL} AS reverse_cost
             FROM trechos_osm t
             LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho
             WHERE t.source IS NOT NULL AND t.target IS NOT NULL',
            vp.v_inicio,
            vp.v_fim,
            directed := false
        ) d
        WHERE d.edge != -1
        ORDER BY d.seq ASC
    ),
    trechos_rota AS (
        SELECT
            rd.seq,
            t.id_trecho,
            t.name,
            t.geom,
            e.status,
            ST_Length(t.geom) AS comprimento,
            rd.cost
        FROM rota_dijkstra rd
        JOIN trechos_osm t ON t.id_trecho = rd.edge
        LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho
        ORDER BY rd.seq ASC
    )
    SELECT
        json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(
                json_agg(
                    json_build_object(
                        'type', 'Feature',
                        'geometry', ST_AsGeoJSON(ST_Transform(tr.geom, 4326))::json,
                        'properties', json_build_object(
                            'id_trecho', tr.id_trecho,
                            'nome', tr.name,
                            'status', tr.status,
                            'comprimento_m', ROUND(tr.comprimento::numeric, 2),
                            'custo_ponderado', ROUND(tr.cost::numeric, 2)
                        )
                    ) ORDER BY tr.seq
                ), '[]'::json
            )
        ) AS rota_geojson,
        COALESCE(ROUND((SUM(tr.comprimento) / 1000.0)::numeric, 2), 0.0) AS distancia_km
    FROM trechos_rota tr;
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

    raw_geojson = row["rota_geojson"]
    if isinstance(raw_geojson, str):
        raw_geojson = json.loads(raw_geojson)

    if not raw_geojson.get("features"):
        raise HTTPException(status_code=404, detail="Não há trajeto viário conectando estes pontos sem vias alagadas.")

    return {
        "rota_geojson": raw_geojson,
        "distancia_km": float(row["distancia_km"]) if row["distancia_km"] else 0.0
    }