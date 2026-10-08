from app.seguranca import require_role
import json
import asyncpg
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.database import get_connection

router = APIRouter(prefix="/api/v1/rotas", tags=["Rotas e Navegação"])

PESO_ALERTA = 10

# Custo dinâmico considerando estado operacional
CUSTO_DINAMICO = f"""CASE
    WHEN e.status = ''INTRANSITAVEL'' THEN ST_Length(t.geom) * 1000.0
    WHEN e.status = ''INTRANSITAVEL_LEVES'' THEN ST_Length(t.geom) * 20.0
    WHEN e.status = ''TRANSITAVEL_ALERTA'' THEN ST_Length(t.geom) * {PESO_ALERTA}
    ELSE ST_Length(t.geom)
END"""

ARESTAS_SEGURAS = f"""SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint,
    {CUSTO_DINAMICO} AS cost, {CUSTO_DINAMICO} AS reverse_cost
FROM trechos_osm t
LEFT JOIN estado_operacional_trechos e ON e.id_trecho = t.id_trecho
WHERE t.source IS NOT NULL AND t.target IS NOT NULL"""

# Arestas puras (distância física) para traçar a rota direta de referência
ARESTAS_PADRAO = """SELECT t.id_trecho AS id, t.source::bigint, t.target::bigint,
    ST_Length(t.geom) AS cost, ST_Length(t.geom) AS reverse_cost
FROM trechos_osm t
WHERE t.source IS NOT NULL AND t.target IS NOT NULL"""

SQL_VERTICE_PROXIMO = """SELECT v.id
FROM trechos_osm_vertices_pgr v
ORDER BY v.the_geom <-> ST_Transform(ST_SetSRID(ST_MakePoint($1, $2), 4326), 31983)
LIMIT 1"""

def montar_query_rota(sql_arestas: str) -> str:
    return f"""WITH caminho AS (
        SELECT seq, edge, cost
        FROM pgr_dijkstra('{sql_arestas}', $1::bigint, $2::bigint, directed := false)
        WHERE edge != -1
    ),
    trechos_rota AS (
        SELECT c.seq, c.cost, t.id_trecho, t.name, t.geom, t.highway, e.status,
               ST_Length(t.geom) AS comprimento,
               -- Estima velocidade média em km/h por tipo de via OSM
               CASE
                   WHEN t.highway IN ('primary', 'trunk') THEN 40.0
                   WHEN t.highway IN ('secondary', 'tertiary') THEN 30.0
                   ELSE 20.0
               END AS vel_kmh
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
                            'tipo_via', tr.highway,
                            'comprimento_m', ROUND(tr.comprimento::numeric, 2)
                        )
                    ) ORDER BY tr.seq
                ), '[]'::json
            )
        ) AS rota_geojson,
        COALESCE(ROUND((SUM(tr.comprimento) / 1000.0)::numeric, 2), 0.0) AS distancia_km,
        COALESCE(ROUND((SUM((tr.comprimento / 1000.0) / tr.vel_kmh * 60.0))::numeric, 1), 0.0) AS tempo_estimado_min,
        BOOL_OR(tr.status IN ('INTRANSITAVEL', 'INTRANSITAVEL_LEVES', 'TRANSITAVEL_ALERTA')) AS cruza_area_risco
    FROM trechos_rota tr"""

SQL_ROTA_SEGURA = montar_query_rota(ARESTAS_SEGURAS)
SQL_ROTA_PADRAO = montar_query_rota(ARESTAS_PADRAO)

SQL_PONTO_ALCANCAVEL = f"""SELECT v.id,
       ST_Y(ST_Transform(v.the_geom, 4326)) AS lat,
       ST_X(ST_Transform(v.the_geom, 4326)) AS lon,
       ST_Distance(v.the_geom,
                   ST_Transform(ST_SetSRID(ST_MakePoint($2, $3), 4326), 31983)) AS dist_destino_m
FROM pgr_drivingDistance('{ARESTAS_SEGURAS}', $1::bigint, 1e12::float8, directed := false) alc
JOIN trechos_osm_vertices_pgr v ON v.id = alc.node
ORDER BY dist_destino_m
LIMIT 1"""

SEM_ROTA = {"type": "FeatureCollection", "features": []}

class RotaRequest(BaseModel):
    origem_lat: float = Field(..., ge=-90, le=90)
    origem_lon: float = Field(..., ge=-180, le=180)
    destino_lat: float = Field(..., ge=-90, le=90)
    destino_lon: float = Field(..., ge=-180, le=180)

async def executar_rota(conn: asyncpg.Connection, sql_query: str, v_inicio: int, v_fim: int):
    row = await conn.fetchrow(sql_query, v_inicio, v_fim)
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
        "tempo_minutos": float(row["tempo_estimado_min"] or 0),
        "cruza_area_risco": bool(row["cruza_area_risco"])
    }

@router.post("/calcular")
async def calcular_rota(dados: RotaRequest, conn: asyncpg.Connection = Depends(get_connection)):
    v_inicio = await conn.fetchval(SQL_VERTICE_PROXIMO, dados.origem_lon, dados.origem_lat)
    v_fim = await conn.fetchval(SQL_VERTICE_PROXIMO, dados.destino_lon, dados.destino_lat)

    if v_inicio is None or v_fim is None:
        raise HTTPException(status_code=404, detail="Nao encontrei a malha viaria perto desses pontos.")

    if v_inicio == v_fim:
        raise HTTPException(status_code=400, detail="Origem e destino caem no mesmo cruzamento.")

    # 1. Traça rota segura (desviando de alagamentos)
    rota_segura = await executar_rota(conn, SQL_ROTA_SEGURA, v_inicio, v_fim)

    # 2. Traça rota de referência (como se não houvesse enchente)
    rota_referencia = await executar_rota(conn, SQL_ROTA_PADRAO, v_inicio, v_fim)

    if rota_segura:
        dist_padrao = rota_referencia["distancia_km"] if rota_referencia else rota_segura["distancia_km"]
        tempo_padrao = rota_referencia["tempo_minutos"] if rota_referencia else rota_segura["tempo_minutos"]

        atraso_min = max(0.0, round(rota_segura["tempo_minutos"] - tempo_padrao, 1))
        km_adicionais = max(0.0, round(rota_segura["distancia_km"] - dist_padrao, 2))

        # Se a rota de referência tocaria vias alagadas, registramos risco evitado
        risco_evitado = bool(rota_referencia and rota_referencia["cruza_area_risco"])

        return {
            "rota_segura": True,
            "mensagem": None,
            "distancia_km": rota_segura["distancia_km"],
            "tempo_estimado_minutos": rota_segura["tempo_minutos"],
            "resumo_logistica": {
                "rota_direta_km": dist_padrao,
                "tempo_direto_minutos": tempo_padrao,
                "desvio_km": km_adicionais,
                "atraso_estimado_minutos": atraso_min,
                "risco_alagamento_evitado": risco_evitado
            },
            "ponto_alternativo": None,
            "rota_geojson": rota_segura["rota_geojson"]
        }

    # Se não há rota segura até o destino final, busca o ponto mais próximo navegável
    alt = await conn.fetchrow(SQL_PONTO_ALCANCAVEL, v_inicio, dados.destino_lon, dados.destino_lat)
    rota_alt = None

    if alt and alt["id"] != v_inicio:
        rota_alt = await executar_rota(conn, SQL_ROTA_SEGURA, v_inicio, alt["id"])

    if not rota_alt or not alt:
        return {
            "rota_segura": False,
            "mensagem": "Nao ha rota segura e nenhum ponto alcancavel sem passar por via intransitavel. Permaneca em local seguro.",
            "distancia_km": 0.0,
            "tempo_estimado_minutos": 0.0,
            "resumo_logistica": None,
            "ponto_alternativo": None,
            "rota_geojson": SEM_ROTA
        }

    return {
        "rota_segura": False,
        "mensagem": "Destino isolado por vias intransitaveis. Rota calculada ate o ponto seguro mais proximo.",
        "distancia_km": rota_alt["distancia_km"],
        "tempo_estimado_minutos": rota_alt["tempo_minutos"],
        "resumo_logistica": {
            "rota_direta_km": rota_referencia["distancia_km"] if rota_referencia else None,
            "tempo_direto_minutos": rota_referencia["tempo_minutos"] if rota_referencia else None,
            "desvio_km": max(0.0, round(rota_alt["distancia_km"] - (rota_referencia["distancia_km"] if rota_referencia else 0), 2)), "atraso_estimado_minutos": max(0.0, round(rota_alt["tempo_minutos"] - (rota_referencia["tempo_minutos"] if rota_referencia else 0), 1)),
            "risco_alagamento_evitado": True
        },
        "ponto_alternativo": {
            "lat": alt["lat"],
            "lon": alt["lon"],
            "distancia_ate_destino_m": round(alt["dist_destino_m"])
        },
        "rota_geojson": rota_alt["rota_geojson"]
    }




@router.get("/intermunicipal", dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "VIEWER"]))])
async def calcular_rota_intermunicipal(
    origem: str = "Araraquara",
    destino: str = "Sao Paulo",
    custo_hora_veiculo: float = 150.0,
    consumo_km_litro: float = 2.5,
    preco_diesel_litro: float = 6.10,
    conn: asyncpg.Connection = Depends(get_connection)
):
    query_corredor = """
        SELECT 
            r.id_trecho,
            r.name,
            ROUND((r.length / 1000.0)::numeric, 1) AS distancia_km,
            ROUND(((r.length / 1000.0) / 80.0 * 60.0)::numeric, 1) AS tempo_nominal_min,
            COALESCE(c.status_pista, 'LIBERADA') AS status_pista,
            COALESCE(c.precipitacao_mm_h, 0.0) AS precipitacao_mm_h,
            COALESCE(c.fator_atraso, 1.0) AS fator_atraso,
            ROUND((((r.length / 1000.0) / 80.0 * 60.0) * COALESCE(c.fator_atraso, 1.0))::numeric, 1) AS tempo_real_min
        FROM corredor_sp_araraquara r
        LEFT JOIN condicoes_corredor c ON c.id_trecho = r.id_trecho
        ORDER BY r.id_trecho;
    """
    segmentos = await conn.fetch(query_corredor)
    
    total_km = sum(float(s["distancia_km"]) for s in segmentos)
    tempo_nominal_total = sum(float(s["tempo_nominal_min"]) for s in segmentos)
    tempo_real_total = sum(float(s["tempo_real_min"]) for s in segmentos)
    
    custo_diesel_km = preco_diesel_litro / consumo_km_litro
    custo_minuto = custo_hora_veiculo / 60.0
    
    trechos_criticos = [s for s in segmentos if s["status_pista"] == "RISCO_CRITICO_ALAGAMENTO"]
    alerta_meteorologico = len(trechos_criticos) > 0
    
    recomendacao = "MANTER_ROTA_PADRAO"
    desvio_sugerido = None
    decisao_economica = None
    
    if alerta_meteorologico:
        adicional_km = 18.4
        tempo_estimado_desvio = tempo_nominal_total + 15.0
        economia_tempo = tempo_real_total - tempo_estimado_desvio
        
        custo_diesel_adicional = adicional_km * custo_diesel_km
        economia_tempo_reais = economia_tempo * custo_minuto
        beneficio_liquido = economia_tempo_reais - custo_diesel_adicional
        
        recomendacao = "DESVIO_RECOMENDADO" if beneficio_liquido > 0 else "AVALIAR_RETENCAO"
        desvio_sugerido = {
            "rota_alternativa": "Eixo SP-215 / SP-330 (Anhanguera via Descalvado / Porto Ferreira)",
            "adicional_km": adicional_km,
            "tempo_estimado_desvio_min": round(tempo_estimado_desvio, 1),
            "economia_tempo_min": round(economia_tempo, 1),
            "motivo": f"{len(trechos_criticos)} trecho(s) com risco critico de intransitabilidade na SP-310"
        }
        decisao_economica = {
            "custo_diesel_extra_brl": round(custo_diesel_adicional, 2),
            "economia_hora_parada_brl": round(economia_tempo_reais, 2),
            "beneficio_liquido_brl": round(beneficio_liquido, 2),
            "roi_decisao": "POSITIVO_ECONOMIA_COMPROVADA" if beneficio_liquido > 0 else "NEUTRO"
        }
        
    return {
        "modalidade": "ROTEAMENTO_PREDITIVO_COM_DECISAO_ECONOMICA",
        "origem": origem,
        "destino": destino,
        "resumo": {
            "distancia_total_km": round(total_km, 1),
            "tempo_nominal_min": round(tempo_nominal_total, 1),
            "tempo_real_estimado_min": round(tempo_real_total, 1),
            "atraso_climatico_min": round(tempo_real_total - tempo_nominal_total, 1),
            "status_geral": "ALERTA_CLIMATICO" if alerta_meteorologico else "CONDICOES_FAVORAVEIS"
        },
        "decisao_logistica": {
            "recomendacao": recomendacao,
            "desvio": desvio_sugerido,
            "analise_financeira": decisao_economica
        },
        "segmentos": [
            {
                "id": s["id_trecho"],
                "nome": s["name"],
                "distancia_km": float(s["distancia_km"]),
                "tempo_nominal_min": float(s["tempo_nominal_min"]),
                "tempo_real_min": float(s["tempo_real_min"]),
                "status": s["status_pista"],
                "precipitacao_mm_h": float(s["precipitacao_mm_h"])
            } for s in segmentos
        ]
    }