import json
import uuid
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any

from app.database import get_connection
from app.schemas import VeiculoCreate, OperacaoCreate, SimulacaoB2BRequest, ParametrosFinanceiros
from app.services.routing_engine import RoutingEngine

router = APIRouter(prefix="/api/v1/logistica", tags=["Logística B2B"])

@router.post("/veiculos")
async def cadastrar_veiculo(dados: VeiculoCreate, conn: asyncpg.Connection = Depends(get_connection)):
    query = """
    INSERT INTO veiculos (id_veiculo, placa, modelo, tipo_veiculo, lat_atual, lon_atual)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (id_veiculo) DO UPDATE
    SET placa = EXCLUDED.placa, modelo = EXCLUDED.modelo, lat_atual = EXCLUDED.lat_atual, lon_atual = EXCLUDED.lon_atual
    RETURNING id_veiculo;
    """
    res = await conn.fetchval(query, dados.id_veiculo, dados.placa, dados.modelo, dados.tipo_veiculo, dados.lat_atual, dados.lon_atual)
    return {"sucesso": True, "id_veiculo": res}

@router.get("/veiculos")
async def listar_veiculos(conn: asyncpg.Connection = Depends(get_connection)):
    rows = await conn.fetch("SELECT * FROM veiculos ORDER BY id_veiculo;")
    return [dict(r) for r in rows]

@router.post("/operacoes")
async def criar_operacao(dados: OperacaoCreate, conn: asyncpg.Connection = Depends(get_connection)):
    rota_inicial = await RoutingEngine.compute_route(
        conn, dados.origem_lon, dados.origem_lat, dados.destino_lon, dados.destino_lat, profile="FASTEST", rain_mm=0.0
    )
    if not rota_inicial:
        raise HTTPException(status_code=400, detail="Não foi possível traçar rota para as coordenadas fornecidas.")

    dist_km = rota_inicial["distancia_km"]
    tempo_min = rota_inicial["tempo_min"]
    custo_estimado = (dist_km * 4.50) + ((tempo_min / 60.0) * 85.0)

    query = """
    INSERT INTO operacoes (
        id_operacao, id_veiculo, origem_nome, origem_lat, origem_lon,
        destino_nome, destino_lat, destino_lon, janela_inicio, janela_fim,
        status, distancia_planejada_km, tempo_planejado_min, custo_estimado
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::timestamp, $10::timestamp, 'PLANNED', $11, $12, $13)
    RETURNING id_operacao;
    """
    await conn.execute(
        query, dados.id_operacao, dados.id_veiculo, dados.origem_nome, dados.origem_lat, dados.origem_lon,
        dados.destino_nome, dados.destino_lat, dados.destino_lon, dados.janela_inicio, dados.janela_fim,
        dist_km, tempo_min, custo_estimado
    )

    trechos_params = [(dados.id_operacao, idx, t_id) for idx, t_id in enumerate(rota_inicial["ids_trechos"])]
    await conn.executemany(
        "INSERT INTO operacao_rotas_trechos (id_operacao, seq, id_trecho) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;",
        trechos_params
    )

    return {
        "sucesso": True,
        "id_operacao": dados.id_operacao,
        "distancia_km": dist_km,
        "tempo_min": tempo_min,
        "custo_estimado_brl": round(custo_estimado, 2)
    }

@router.get("/operacoes")
async def listar_operacoes(conn: asyncpg.Connection = Depends(get_connection)):
    rows = await conn.fetch("SELECT * FROM operacoes ORDER BY criado_em DESC;")
    return [dict(r) for r in rows]

@router.post("/simular-impacto")
async def simular_impacto(dados: SimulacaoB2BRequest, conn: asyncpg.Connection = Depends(get_connection)):
    id_cenario = f"SIM_{int(dados.precipitacao_mm)}MM_{uuid.uuid4().hex[:6]}"
    await conn.execute(
        "INSERT INTO cenarios_clima (id_cenario, nome, precipitacao_mm, tipo) VALUES ($1, $2, $3, 'SIMULACAO');",
        id_cenario, f"Simulação {dados.precipitacao_mm} mm", dados.precipitacao_mm
    )

    fator_chuva = min(1.0, dados.precipitacao_mm / 100.0)

    query_ops = """
    SELECT 
        o.id_operacao, 
        o.id_veiculo,
        o.origem_lon, o.origem_lat, o.destino_lon, o.destino_lat,
        o.distancia_planejada_km, o.tempo_planejado_min,
        COUNT(t.id_trecho) AS total_trechos,
        COUNT(t.id_trecho) FILTER (WHERE (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * $1)) >= 80.0) AS trechos_criticos,
        COUNT(t.id_trecho) FILTER (WHERE (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * $1)) >= 60.0 AND (COALESCE(t.ivi_score, 0.0) * (0.6 + 0.6 * $1)) < 80.0) AS trechos_risco
    FROM operacoes o
    JOIN operacao_rotas_trechos ort ON ort.id_operacao = o.id_operacao
    JOIN trechos_osm t ON t.id_trecho = ort.id_trecho
    GROUP BY o.id_operacao, o.id_veiculo, o.origem_lon, o.origem_lat, o.destino_lon, o.destino_lat, o.distancia_planejada_km, o.tempo_planejado_min;
    """

    ops = await conn.fetch(query_ops, fator_chuva)

    total_avaliadas = len(ops)
    normais = 0
    atencao = 0
    em_risco = 0
    criticas = 0
    recomendacoes_resumo = []

    custo_km = dados.parametros_custo.custo_por_km
    custo_hora = dados.parametros_custo.custo_hora_motorista + dados.parametros_custo.custo_operacional_veiculo_hora

    for op in ops:
        c_count = op["trechos_criticos"]
        r_count = op["trechos_risco"]

        if c_count > 0:
            nivel = "CRITICO"
            criticas += 1
        elif r_count > 0:
            nivel = "RISCO"
            em_risco += 1
        else:
            nivel = "NORMAL"
            normais += 1

        if nivel in ("CRITICO", "RISCO"):
            rota_segura = await RoutingEngine.compute_route(
                conn, op["origem_lon"], op["origem_lat"], op["destino_lon"], op["destino_lat"],
                profile="SAFEST", rain_mm=dados.precipitacao_mm
            )

            if rota_segura:
                km_add = max(0.0, rota_segura["distancia_km"] - float(op["distancia_planejada_km"]))
                min_add = max(0.0, rota_segura["tempo_min"] - float(op["tempo_planejado_min"]))
                custo_desvio = (km_add * custo_km) + ((min_add / 60.0) * custo_hora)
                prejuizo_evitado = dados.parametros_custo.prejuizo_potencial_alagamento

                motivo = f"Detectados {c_count} trechos bloqueados e {r_count} em risco de inundação na rota planejada."
                
                await conn.execute("""
                INSERT INTO recomendacoes_operacao (
                    id_operacao, id_cenario, tipo_acao, nivel_risco, motivo, confianca,
                    km_adicionais, minutos_adicionais, custo_desvio, prejuizo_potencial_evitado, rota_alternativa_geojson
                ) VALUES ($1, $2, 'ALTERAR_ROTA', $3, $4, 0.88, $5, $6, $7, $8, $9);
                """, op["id_operacao"], id_cenario, nivel, motivo, km_add, min_add, custo_desvio, prejuizo_evitado, json.dumps(rota_segura["geojson"]))

                recomendacoes_resumo.append({
                    "id_operacao": op["id_operacao"],
                    "id_veiculo": op["id_veiculo"],
                    "nivel_risco": nivel,
                    "acao": "ALTERAR_ROTA",
                    "motivo": motivo,
                    "impacto": {
                        "km_adicionais": round(km_add, 2),
                        "minutos_adicionais": round(min_add, 1),
                        "custo_desvio_brl": round(custo_desvio, 2),
                        "prejuizo_potencial_evitado_brl": round(prejuizo_evitado, 2)
                    }
                })

    return {
        "id_cenario": id_cenario,
        "clima_simulado_mm": dados.precipitacao_mm,
        "resumo_operacional": {
            "total_operacoes": total_avaliadas,
            "normais": normais,
            "atencao": atencao,
            "em_risco": em_risco,
            "criticas": criticas
        },
        "recomendacoes": recomendacoes_resumo
    }
