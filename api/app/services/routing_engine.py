import time
import json
import asyncpg
from typing import Dict, Any, Optional, Tuple

class RoutingEngine:
    _cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    _cache_ttl_seconds: float = 300.0
    _max_cache_size: int = 5000

    @classmethod
    def _make_cache_key(cls, orig_lon: float, orig_lat: float, dest_lon: float, dest_lat: float, profile: str, rain_mm: float) -> str:
        return f"{round(orig_lon, 5)}:{round(orig_lat, 5)}_{round(dest_lon, 5)}:{round(dest_lat, 5)}_{profile}_{round(rain_mm, 1)}"

    @classmethod
    def _get_from_cache(cls, key: str) -> Optional[Dict[str, Any]]:
        agora = time.time()
        if key in cls._cache:
            timestamp, data = cls._cache[key]
            if agora - timestamp < cls._cache_ttl_seconds:
                return data
            del cls._cache[key]
        return None

    @classmethod
    def _set_cache(cls, key: str, data: Dict[str, Any]):
        if len(cls._cache) >= cls._max_cache_size:
            antigos = sorted(cls._cache.keys(), key=lambda k: cls._cache[k][0])[:500]
            for k in antigos:
                cls._cache.pop(k, None)
        cls._cache[key] = (time.time(), data)

    @classmethod
    async def compute_route(
        cls,
        conn: asyncpg.Connection,
        orig_lon: float,
        orig_lat: float,
        dest_lon: float,
        dest_lat: float,
        profile: str = "FASTEST",
        rain_mm: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        cache_key = cls._make_cache_key(orig_lon, orig_lat, dest_lon, dest_lat, profile, rain_mm)
        cached_result = cls._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result

        vert_query = """
        SELECT id FROM trechos_osm_vertices_pgr
        ORDER BY the_geom <-> ST_Transform(ST_SetSRID(ST_Point($1, $2), 4326), ST_SRID(the_geom))
        LIMIT 1;
        """
        orig_vert = await conn.fetchval(vert_query, orig_lon, orig_lat)
        dest_vert = await conn.fetchval(vert_query, dest_lon, dest_lat)

        if not orig_vert or not dest_vert or orig_vert == dest_vert:
            return None

        fator_chuva = min(1.0, rain_mm / 100.0)

        if profile == "SAFEST":
            cost_sql = f"""
            CASE 
                WHEN (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * {fator_chuva})) >= 80.0 THEN -1
                WHEN (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * {fator_chuva})) >= 60.0 THEN t.length * 15.0
                ELSE t.length * (1.0 + (COALESCE(t.ivi_score, 0.0) / 10.0))
            END
            """
        elif profile == "BALANCED":
            cost_sql = f"""
            t.length * (1.0 + ((COALESCE(t.ivi_score, 0.0) * (0.5 + 0.5 * {fator_chuva})) / 20.0))
            """
        elif profile == "SHORTEST":
            cost_sql = "t.length"
        else:
            cost_sql = "t.length / NULLIF(COALESCE(t.speed_kph, 40.0), 0.0)"

        pgr_query = f"""
        SELECT 
            r.seq, 
            r.node, 
            r.edge, 
            r.cost, 
            t.id_trecho, 
            t.name, 
            t.length,
            ST_AsGeoJSON(ST_Transform(t.geom, 4326)) AS geojson
        FROM pgr_dijkstra(
            'SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint, ({cost_sql})::float AS cost, ({cost_sql})::float AS reverse_cost FROM trechos_osm t',
            $1::bigint, $2::bigint, false
        ) r
        LEFT JOIN trechos_osm t ON t.id_trecho = r.edge
        WHERE r.edge != -1
        ORDER BY r.seq;
        """

        rows = await conn.fetch(pgr_query, int(orig_vert), int(dest_vert))
        if not rows:
            return None

        total_length = 0.0
        trecho_ids = []
        features = []

        for row in rows:
            l = float(row["length"] or 0.0)
            total_length += l
            trecho_ids.append(int(row["id_trecho"]))
            if row["geojson"]:
                features.append({
                    "type": "Feature",
                    "geometry": json.loads(row["geojson"]),
                    "properties": {
                        "id_trecho": row["id_trecho"],
                        "name": row["name"],
                        "length": l
                    }
                })

        dist_km = round(total_length / 1000.0, 2)
        tempo_min = round((dist_km / 35.0) * 60.0, 1)

        result = {
            "distancia_km": dist_km,
            "tempo_min": tempo_min,
            "ids_trechos": trecho_ids,
            "geojson": {
                "type": "FeatureCollection",
                "features": features
            }
        }

        cls._set_cache(cache_key, result)
        return result

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()

    @classmethod
    def cache_stats(cls) -> Dict[str, Any]:
        return {
            "total_entradas": len(cls._cache),
            "max_capacidade": cls._max_cache_size,
            "ttl_segundos": cls._cache_ttl_seconds
        }
