import json
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.database import get_connection

router = APIRouter(prefix="/api/v1/rotas", tags=["Rotas e Navegação"])

PESO_ALERTA = 10
PESO_LEVES = 100

CUSTO = f"""CASE
    WHEN e.status IN (''INTRANSITAVEL'', ''INTRANSITAVEL_LEVES'') THEN -1
    WHEN e.status = ''TRANSITAVEL_ALERTA'' THEN ST_Length(t.geom) * {PESO_ALERTA}
    ELSE ST_Length(t.geom)
END"""

ARESTAS = f"""SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint,
    {CUSTO} AS cost, {CUSTO} AS reverse_cost
FROM trechos_osm t
LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho
WHERE t.source IS NOT NULL AND t.target IS NOT NULL"""

SQL_VERTICE_PROXIMO = """SELECT v.id
FROM trechos_osm_vertices_pgr v
ORDER BY v.the_geom <-> ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 31983)
LIMIT 1"""

SQL_ROTA = f"""WITH caminho AS (
    SELECT seq, edge, cost
    FROM pgr_dijkstra('{ARESTAS}', $1::bigint, $2::bigint, directed := false)
    WHERE edge != -1
),
trechos_rota AS (
    SELECT c.seq, c.cost, t.id_trecho, t.name, t.geom, e.status,
           ST_Length(t.geom) AS comprimento
    FROM caminho c
    JOIN trechos_osm t ON t.id_trecho = c.edge
    LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho
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
FROM trechos_rota tr"""


SQL_PONTO_ALCANCAVEL = f"""SELECT v.id,
       ST_Y(ST_Transform(v.the_geom, 4326)) AS lat,
       ST_X(ST_Transform(v.the_geom, 4326)) AS lon,
       ST_Distance(v.the_geom,
                   ST_Transform(ST_SetSRID(ST_MakePoint($2, $3), 4326), 31983)) AS dist_destino_m
FROM pgr_drivingDistance('{ARESTAS}', $1::bigint, 1e12::float8, directed := false) alc
JOIN trechos_osm_vertices_pgr v ON v.id = alc.node
ORDER BY dist_destino_m
LIMIT 1"""

SEM_ROTA = {"type": "FeatureCollection", "features": []}

class RotaRequest(BaseModel):
    origem_lat: float = Field(..., ge=-90, le=90)
    origem_lon: float = Field(..., ge=-180, le=180)
    destino_lat: float = Field(..., ge=-90, le=90)
    destino_lon: float = Field(..., ge=-180, le=180)

async def buscar_rota(conn: asyncpg.Connection, v_inicio: int, v_fim: int):
    row = await conn.fetchrow(SQL_ROTA, v_inicio, v_fim)
    if not row or not row["rota_geojson"]:
        return None
    geojson = row["rota_geojson"]
    if isinstance(geojson, str):
        geojson = json.loads(geojson)
    if not geojson.get("features"):
        return None
    return {
        "rota_geojson": geojson,
        "distancia_km": float(row["distancia_km"] or 0),
    }

@router.post("/calcular")
async def calcular_rota(dados: RotaRequest, conn: asyncpg.Connection = Depends(get_connection)):
    v_inicio = await conn.fetchval(SQL_VERTICE_PROXIMO, dados.origem_lon, dados.origem_lat)
    v_fim = await conn.fetchval(SQL_VERTICE_PROXIMO, dados.destino_lon, dados.destino_lat)

    if v_inicio is None or v_fim is None:
        raise HTTPException(status_code=404, detail="Não encontrei a malha viária perto desses pontos.")

    if v_inicio == v_fim:
        raise HTTPException(status_code=400, detail="Origem e destino caem no mesmo cruzamento.")

    rota = await buscar_rota(conn, v_inicio, v_fim)
    if rota:
        return {"rota_segura": True, "mensagem": None, "ponto_alternativo": None, **rota}


    alt = await conn.fetchrow(SQL_PONTO_ALCANCAVEL, v_inicio, dados.destino_lon, dados.destino_lat)
    rota_alt = None

    if alt and alt["id"] != v_inicio:
        rota_alt = await buscar_rota(conn, v_inicio, alt["id"])

    if not rota_alt or not alt:
        return {
            "rota_segura": False,
            "mensagem": "Não há rota segura e nenhum ponto alcançável sem passar por via intransitável. Permaneça em local seguro e acione a Defesa Civil.",
            "ponto_alternativo": None,
            "rota_geojson": SEM_ROTA,
            "distancia_km": 0.0,
        }

    return {
        "rota_segura": False,
        "mensagem": "Não há rota segura até o destino. Esta rota leva ao ponto mais próximo que ainda dá para alcançar sem passar por via intransitável.",
        "ponto_alternativo": {
            "lat": alt["lat"],
            "lon": alt["lon"],
            "distancia_ate_destino_m": round(alt["dist_destino_m"]),
        },
        **rota_alt,
    }