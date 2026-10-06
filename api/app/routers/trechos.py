import json
import asyncpg
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.database import get_connection

router = APIRouter(prefix="/api/v1/trechos", tags=["Trechos Viarios"])

@router.get("/geojson")
async def get_trechos_geojson(
    classe: Optional[str] = None,
    limit: int = 35000,
    conn: asyncpg.Connection = Depends(get_connection)
):
    query = """
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(json_agg(
                json_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(ST_Transform(t.geom, 4326))::json,
                    'properties', json_build_object(
                        'id_trecho', t.id_trecho,
                        'nome', t.name,
                        'tipo_via', t.highway,
                        'ivi', t.ivi_score,
                        'classe_risco', COALESCE(t.classe_risco, 'Baixo'),
                        'altitude_media', ROUND(COALESCE(t.altitude_media, 0)::numeric, 1),
                        'distancia_agua_m', ROUND(COALESCE(t.distancia_agua_m, 0)::numeric, 1),
                        'total_alagamentos', COALESCE(t.total_alagamentos, 0),
                        'status_operacional', COALESCE(e.status, 'TRANSITAVEL'),
                        'severidade', COALESCE(e.severidade, 'VERDE'),
                        'relato_origem', e.relato_origem
                    )
                )
            ), '[]'::json)
        )
        FROM (
            SELECT id_trecho, name, highway, ivi_score, classe_risco, altitude_media, distancia_agua_m, total_alagamentos, geom
            FROM trechos_osm
            WHERE ($1::text IS NULL OR LOWER(classe_risco) = LOWER($1))
            ORDER BY id_trecho
            LIMIT $2
        ) t
        LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho;
    """
    row = await conn.fetchval(query, classe, limit)
    return JSONResponse(content=json.loads(row))
