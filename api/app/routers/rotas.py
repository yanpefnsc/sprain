from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import asyncpg

from app.database import get_connection

router = APIRouter(prefix="/api/v1/rotas", tags=["Logistica & Roteamento Resiliente"])

SQL_VERTICE_PROXIMO = """
    SELECT id 
    FROM trechos_osm_vertices_pgr 
    ORDER BY the_geom <-> ST_SetSRID(ST_Point($1, $2), 4326) 
    LIMIT 1;
"""

SQL_ARESTAS_PADRAO = """
    SELECT id, source, target, st_length(the_geom, true) as cost 
    FROM trechos_osm
"""

SQL_ARESTAS_RESILIENTE = """
    SELECT 
        t.id, 
        t.source, 
        t.target, 
        (st_length(t.the_geom, true) * (1.0 + (COALESCE(o.severidade, 0) * 10.0))) as cost 
    FROM trechos_osm t
    LEFT JOIN ocorrencias_alagamento o 
        ON ST_DWithin(t.the_geom::geography, o.geom::geography, 30.0) 
        AND o.status = 'ativa'
"""

def montar_query_rota(sql_arestas: str) -> str:
    return f"""WITH caminho AS (
        SELECT seq, edge, cost 
        FROM pgr_dijkstra('{sql_arestas}', $1::bigint, $2::bigint, directed := false)
    )
    SELECT 
        COALESCE(SUM(c.cost), 0.0) as distancia_metros,
        ST_AsGeoJSON(ST_LineMerge(ST_Collect(t.the_geom))) as rota_geojson
    FROM caminho c
    JOIN trechos_osm t ON c.edge = t.id;"""

class RotaRequest(BaseModel):
    origem_lat: float = Field(..., ge=-90.0, le=90.0)
    origem_lon: float = Field(..., ge=-180.0, le=180.0)
    destino_lat: float = Field(..., ge=-90.0, le=90.0)
    destino_lon: float = Field(..., ge=-180.0, le=180.0)

async def executar_rota(conn: asyncpg.Connection, sql_query: str, v_inicio: int, v_fim: int):
    row = await conn.fetchrow(sql_query, v_inicio, v_fim)
    if not row or not row["rota_geojson"]:
        return None
    return {
        "distancia_km": round(float(row["distancia_metros"]) / 1000.0, 2),
        "geojson": row["rota_geojson"]
    }

@router.post("/calcular")
async def calcular_rota(dados: RotaRequest, conn: asyncpg.Connection = Depends(get_connection)):
    v_inicio = await conn.fetchval(SQL_VERTICE_PROXIMO, dados.origem_lon, dados.origem_lat)
    v_fim = await conn.fetchval(SQL_VERTICE_PROXIMO, dados.destino_lon, dados.destino_lat)
    
    if not v_inicio or not v_fim:
        raise HTTPException(status_code=404, detail="Origem ou destino fora da malha viaria.")

    rota_padrao = await executar_rota(conn, montar_query_rota(SQL_ARESTAS_PADRAO), v_inicio, v_fim)
    rota_resiliente = await executar_rota(conn, montar_query_rota(SQL_ARESTAS_RESILIENTE), v_inicio, v_fim)

    if not rota_padrao or not rota_resiliente:
        raise HTTPException(status_code=404, detail="Nao foi possivel tracar uma rota entre os pontos.")

    return {
        "rota_padrao": rota_padrao,
        "rota_resiliente": rota_resiliente,
        "desvio_necessario": rota_padrao["distancia_km"] != rota_resiliente["distancia_km"]
    }

@router.get("/intermunicipal")
async def calcular_rota_intermunicipal(
    origem: str = Query("Araraquara", description="Cidade de origem do transporte"),
    destino: str = Query("Sao Paulo", description="Cidade de destino final"),
    tipo_veiculo: str = Query("TRUCK_3_EIXOS", description="Categoria: VUC, TRUCK_3_EIXOS ou CARRETA_5_EIXOS"),
    custo_hora_veiculo: float = Query(150.0, ge=10.0, description="Custo operacional por hora parada (R$)"),
    consumo_km_litro: float = Query(2.5, ge=0.5, description="Consumo medio de diesel (km/l)"),
    preco_diesel_litro: float = Query(6.10, ge=1.0, description="Preco do diesel (R$/l)"),
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
    
    # Resolucao de tarifas de pedagio da malha por categoria
    coluna_tarifa = "tarifa_truck_3eixos"
    if tipo_veiculo.upper() == "VUC":
        coluna_tarifa = "tarifa_vuc"
    elif tipo_veiculo.upper() == "CARRETA_5_EIXOS":
        coluna_tarifa = "tarifa_carreta_5eixos"

    query_pedagios = f"""
        SELECT 
            id, rodovia, km, municipio, concessionaria,
            {coluna_tarifa} AS tarifa
        FROM pracas_pedagio
        ORDER BY km DESC;
    """
    pracas_banco = await conn.fetch(query_pedagios)

    pedagios_rota = [
        {
            "id": p["id"],
            "rodovia": p["rodovia"],
            "km": float(p["km"]),
            "municipio": p["municipio"],
            "concessionaria": p["concessionaria"],
            "tarifa": float(p["tarifa"])
        }
        for p in pracas_banco
    ]
    custo_pedagio_total = sum(p["tarifa"] for p in pedagios_rota)

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
        
        recomendacao = "DESVIO_RECOMENDADO" if beneficio_liquido > 0 else "MANTER_ROTA_COM_ATENCAO"
        
        desvio_sugerido = {
            "via_alternativa": "Variante SP-330 / Vicinal de Apoio",
            "distancia_adicional_km": adicional_km,
            "distancia_total_km": round(total_km + adicional_km, 1),
            "tempo_estimado_min": round(tempo_estimado_desvio, 1),
            "tempo_economizado_min": round(economia_tempo, 1)
        }
        
        decisao_economica = {
            "custo_diesel_adicional_reais": round(custo_diesel_adicional, 2),
            "economia_tempo_reais": round(economia_tempo_reais, 2),
            "custo_pedagio_rota_reais": round(custo_pedagio_total, 2),
            "beneficio_liquido_reais": round(beneficio_liquido, 2),
            "roi_positivo": beneficio_liquido > 0
        }
    else:
        decisao_economica = {
            "custo_diesel_adicional_reais": 0.0,
            "economia_tempo_reais": 0.0,
            "custo_pedagio_rota_reais": round(custo_pedagio_total, 2),
            "beneficio_liquido_reais": 0.0,
            "roi_positivo": True
        }

    return {
        "status": "OPERACIONAL",
        "modalidade": "ROTEAMENTO_PREDITIVO_COM_DECISAO_ECONOMICA",
        "origem": origem,
        "destino": destino,
        "tipo_veiculo": tipo_veiculo.upper(),
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
        "pedagios": {
            "quantidade_pracas": len(pedagios_rota),
            "custo_total_pedagio_reais": round(custo_pedagio_total, 2),
            "pracas_detalhadas": pedagios_rota
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
            }
            for s in segmentos
        ]
    }