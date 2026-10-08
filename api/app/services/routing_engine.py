import json
import asyncpg
from typing import Dict, Any, Optional

SQL_VERTICE = """
SELECT v.id
FROM trechos_osm_vertices_pgr v
ORDER BY v.the_geom <-> ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 31983)
LIMIT 1;
"""

class RoutingEngine:
    @staticmethod
    def build_edge_query(profile: str, rain_mm: float) -> str:
        if profile == "FASTEST":
            cost_exp = "ST_Length(t.geom) / CASE WHEN t.highway IN ('primary', 'trunk') THEN 40.0 WHEN t.highway IN ('secondary', 'tertiary') THEN 30.0 ELSE 20.0 END"
            return f"""SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint, {cost_exp} AS cost, {cost_exp} AS reverse_cost FROM trechos_osm t WHERE t.source IS NOT NULL AND t.target IS NOT NULL"""
        
        if profile == "SHORTEST":
            return """SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint, ST_Length(t.geom) AS cost, ST_Length(t.geom) AS reverse_cost FROM trechos_osm t WHERE t.source IS NOT NULL AND t.target IS NOT NULL"""

        fator_chuva = min(1.0, rain_mm / 100.0)
        
        if profile == "SAFEST":
            mult_critico = "5000.0"
            mult_risco = "100.0"
            mult_atencao = "10.0"
        else:
            mult_critico = "1000.0"
            mult_risco = "25.0"
            mult_atencao = "4.0"

        cost_case = f"""
        CASE 
            WHEN (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * {fator_chuva})) >= 80.0 THEN ST_Length(t.geom) * {mult_critico}
            WHEN (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * {fator_chuva})) >= 60.0 THEN ST_Length(t.geom) * {mult_risco}
            WHEN (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * {fator_chuva})) >= 40.0 THEN ST_Length(t.geom) * {mult_atencao}
            ELSE ST_Length(t.geom)
        END
        """
        return f"""SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint, {cost_case} AS cost, {cost_case} AS reverse_cost FROM trechos_osm t WHERE t.source IS NOT NULL AND t.target IS NOT NULL"""

    @classmethod
    async def compute_route(cls, conn: asyncpg.Connection, orig_lon: float, orig_lat: float, dest_lon: float, dest_lat: float, profile: str = "BALANCED", rain_mm: float = 0.0) -> Optional[Dict[str, Any]]:
        v_orig = await conn.fetchval(SQL_VERTICE, orig_lon, orig_lat)
        v_dest = await conn.fetchval(SQL_VERTICE, dest_lon, dest_lat)

        if not v_orig or not v_dest or v_orig == v_dest:
            return None

        sql_edges = cls.build_edge_query(profile, rain_mm)
        fator_chuva = min(1.0, rain_mm / 100.0)

        query = f"""
        WITH dijkstra AS (
            SELECT seq, edge, cost
            FROM pgr_dijkstra('{sql_edges}', $1::bigint, $2::bigint, directed := false)
            WHERE edge != -1
        ),
        rota AS (
            SELECT 
                d.seq, 
                t.id_trecho, 
                t.name, 
                t.geom, 
                t.highway, 
                ST_Length(t.geom) AS comp_m,
                COALESCE(t.ivi_score, 0.0) as ivi_base,
                (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * {fator_chuva})) AS dynamic_score,
                CASE 
                    WHEN t.highway IN ('primary', 'trunk') THEN 40.0
                    WHEN t.highway IN ('secondary', 'tertiary') THEN 30.0
                    ELSE 20.0
                END AS vel_kmh
            FROM dijkstra d
            JOIN trechos_osm t ON t.id_trecho = d.edge
        )
        SELECT 
            json_build_object(
                'type', 'FeatureCollection',
                'features', COALESCE(
                    json_agg(
                        json_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(ST_Transform(r.geom, 4326))::json,
                            'properties', json_build_object(
                                'id_trecho', r.id_trecho,
                                'nome', r.name,
                                'ivi_dinamico', ROUND(r.dynamic_score::numeric, 1),
                                'comprimento_m', ROUND(r.comp_m::numeric, 2)
                            )
                        ) ORDER BY r.seq
                    ), '[]'::json
                )
            ) AS geojson,
            COALESCE(ROUND((SUM(r.comp_m) / 1000.0)::numeric, 2), 0.0) AS distancia_km,
            COALESCE(ROUND((SUM((r.comp_m / 1000.0) / r.vel_kmh * 60.0))::numeric, 1), 0.0) AS tempo_min,
            COALESCE(ROUND(AVG(r.dynamic_score)::numeric, 1), 0.0) AS risco_medio,
            COALESCE(ROUND(MAX(r.dynamic_score)::numeric, 1), 0.0) AS risco_maximo,
            COUNT(*) FILTER (WHERE r.dynamic_score >= 80.0)::int AS trechos_criticos,
            COUNT(*) FILTER (WHERE r.dynamic_score >= 60.0 AND r.dynamic_score < 80.0)::int AS trechos_risco,
            array_agg(r.id_trecho ORDER BY r.seq) AS ids_trechos
        FROM rota r;
        """

        row = await conn.fetchrow(query, v_orig, v_dest)
        if not row or not row["geojson"] or not row["ids_trechos"]:
            return None

        geojson = row["geojson"]
        if isinstance(geojson, str):
            geojson = json.loads(geojson)

        return {
            "profile": profile,
            "distancia_km": float(row["distancia_km"]),
            "tempo_min": float(row["tempo_min"]),
            "risco_medio": float(row["risco_medio"]),
            "risco_maximo": float(row["risco_maximo"]),
            "trechos_criticos": int(row["trechos_criticos"]),
            "trechos_risco": int(row["trechos_risco"]),
            "ids_trechos": list(row["ids_trechos"]),
            "geojson": geojson
        }
