from fastapi import Request, APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
import io
import csv
import json
import uuid
import asyncpg
import urllib.request
from typing import List, Dict, Any, Optional

from app.services.rate_limiter import TenantRateLimiter
from app.seguranca import require_role, get_current_user_claims
from app.database import get_connection
from app.schemas import (
    VeiculoCreate,
    OperacaoCreate,
    SimulacaoB2BRequest,
    WebhookAlertaRequest,
    PlanejamentoD1Request,
    ParametrosFinanceiros
)
from app.services.routing_engine import RoutingEngine
from app.url_segura import is_safe_url

router = APIRouter(prefix="/api/v1/logistica", tags=["Logistica B2B"])

class _SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener_seguro = urllib.request.build_opener(_SemRedirect)


async def aplicar_rate_limit(request: Request, claims: dict = Depends(get_current_user_claims)):
    limite, restantes = TenantRateLimiter.check_rate_limit(claims["tenant_id"])
    request.state.ratelimit_limit = limite
    request.state.ratelimit_remaining = restantes

def resolve_tenant(x_tenant_id: Optional[str] = Header(None), tenant_id: Optional[str] = Query(None), claims: dict = Depends(get_current_user_claims)) -> str:
    tenant_autenticado = claims["tenant_id"]
    tenant_solicitado = x_tenant_id or tenant_id
    if tenant_solicitado and tenant_solicitado != tenant_autenticado:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return tenant_autenticado

@router.post("/veiculos", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"])), Depends(aplicar_rate_limit)])
async def cadastrar_veiculo(dados: VeiculoCreate, conn: asyncpg.Connection = Depends(get_connection), tenant_id: str = Depends(resolve_tenant)):
    dados.tenant_id = tenant_id
    query = """
    INSERT INTO veiculos (id_veiculo, placa, modelo, tipo_veiculo, lat_atual, lon_atual, tenant_id)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (id_veiculo) DO UPDATE
    SET placa = EXCLUDED.placa, modelo = EXCLUDED.modelo, lat_atual = EXCLUDED.lat_atual, lon_atual = EXCLUDED.lon_atual, tenant_id = EXCLUDED.tenant_id
    RETURNING id_veiculo;
    """
    res = await conn.fetchval(query, dados.id_veiculo, dados.placa, dados.modelo, dados.tipo_veiculo, dados.lat_atual, dados.lon_atual, dados.tenant_id)
    return {"sucesso": True, "id_veiculo": res, "tenant_id": dados.tenant_id}

@router.get("/veiculos", dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "VIEWER"])), Depends(aplicar_rate_limit)])
async def listar_veiculos(tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    rows = await conn.fetch("SELECT * FROM veiculos WHERE tenant_id = $1 ORDER BY id_veiculo;", tenant_id)
    return [dict(r) for r in rows]

@router.post("/operacoes", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"])), Depends(aplicar_rate_limit)])
async def criar_operacao(dados: OperacaoCreate, conn: asyncpg.Connection = Depends(get_connection), tenant_id: str = Depends(resolve_tenant)):
    dados.tenant_id = tenant_id
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
        status, distancia_planejada_km, tempo_planejado_min, custo_estimado, tenant_id
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::timestamp, $10::timestamp, 'PLANNED', $11, $12, $13, $14)
    RETURNING id_operacao;
    """
    await conn.execute(
        query, dados.id_operacao, dados.id_veiculo, dados.origem_nome, dados.origem_lat, dados.origem_lon,
        dados.destino_nome, dados.destino_lat, dados.destino_lon, dados.janela_inicio, dados.janela_fim,
        dist_km, tempo_min, custo_estimado, dados.tenant_id
    )

    trechos_params = [(dados.id_operacao, idx, t_id) for idx, t_id in enumerate(rota_inicial["ids_trechos"])]
    await conn.executemany(
        "INSERT INTO operacao_rotas_trechos (id_operacao, seq, id_trecho) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;",
        trechos_params
    )

    return {
        "sucesso": True,
        "id_operacao": dados.id_operacao,
        "tenant_id": dados.tenant_id,
        "distancia_km": dist_km,
        "tempo_min": tempo_min,
        "custo_estimado_brl": round(custo_estimado, 2)
    }

@router.get("/operacoes")
async def listar_operacoes(tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    rows = await conn.fetch("SELECT * FROM operacoes WHERE tenant_id = $1 ORDER BY criado_em DESC;", tenant_id)
    return [dict(r) for r in rows]

@router.post("/simular-impacto", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"])), Depends(aplicar_rate_limit)])
async def simular_impacto(dados: SimulacaoB2BRequest, conn: asyncpg.Connection = Depends(get_connection), tenant_id: str = Depends(resolve_tenant)):
    dados.tenant_id = tenant_id
    id_cenario = f"SIM_{int(dados.precipitacao_mm)}MM_{uuid.uuid4().hex[:6]}"
    await conn.execute(
        "INSERT INTO cenarios_clima (id_cenario, nome, precipitacao_mm, tipo, tenant_id) VALUES ($1, $2, $3, 'SIMULACAO', $4);",
        id_cenario, f"Simulação {dados.precipitacao_mm} mm", dados.precipitacao_mm, dados.tenant_id
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
    WHERE o.tenant_id = $2
    GROUP BY o.id_operacao, o.id_veiculo, o.origem_lon, o.origem_lat, o.destino_lon, o.destino_lat, o.distancia_planejada_km, o.tempo_planejado_min;
    """

    ops = await conn.fetch(query_ops, fator_chuva, dados.tenant_id)

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
                    km_adicionais, minutos_adicionais, custo_desvio, prejuizo_potencial_evitado, rota_alternativa_geojson, tenant_id
                ) VALUES ($1, $2, 'ALTERAR_ROTA', $3, $4, 0.88, $5, $6, $7, $8, $9, $10);
                """, op["id_operacao"], id_cenario, nivel, motivo, km_add, min_add, custo_desvio, prejuizo_evitado, json.dumps(rota_segura["geojson"]), dados.tenant_id)

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
        "tenant_id": dados.tenant_id,
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

@router.get("/operacoes/{id_operacao}/explicacao")
async def obter_explicacao_decisao(id_operacao: str, tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    op = await conn.fetchrow("SELECT * FROM operacoes WHERE id_operacao = $1 AND tenant_id = $2;", id_operacao, tenant_id)
    if not op:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")

    veiculo = await conn.fetchrow("SELECT placa, modelo, tipo_veiculo FROM veiculos WHERE id_veiculo = $1 AND tenant_id = $2;", op["id_veiculo"], tenant_id)
    rec = await conn.fetchrow("""
        SELECT tipo_acao, nivel_risco, motivo, confianca, km_adicionais, minutos_adicionais, custo_desvio, prejuizo_potencial_evitado
        FROM recomendacoes_operacao
        WHERE id_operacao = $1 AND tenant_id = $2
        ORDER BY id_recomendacao DESC LIMIT 1;
    """, id_operacao, tenant_id)

    trechos_criticos = await conn.fetch("""
        SELECT t.id_trecho, t.name, t.length, t.classe_risco, t.ivi_score
        FROM operacao_rotas_trechos ort
        JOIN trechos_osm t ON t.id_trecho = ort.id_trecho
        WHERE ort.id_operacao = $1 AND t.classe_risco IN ('Alto', 'Critico', 'Muito Alto')
        ORDER BY t.ivi_score DESC;
    """, id_operacao)

    dist_orig = float(op["distancia_planejada_km"] or 0.0)
    delta_km = float(rec["km_adicionais"]) if rec and rec["km_adicionais"] is not None else 0.0
    dist_alt = round(dist_orig + delta_km, 2)

    tempo_orig = float(op["tempo_planejado_min"] or 0.0)
    delta_tempo = float(rec["minutos_adicionais"]) if rec and rec["minutos_adicionais"] is not None else 0.0
    tempo_alt = round(tempo_orig + delta_tempo, 2)

    custo_desvio = float(rec["custo_desvio"]) if rec and rec["custo_desvio"] is not None else round((delta_km * 4.50) + ((delta_tempo / 60.0) * 85.0), 2)
    prejuizo_evitado = float(rec["prejuizo_potencial_evitado"]) if rec and rec["prejuizo_potencial_evitado"] is not None else 0.0

    pontos_bloqueio = [
        {
            "id_trecho": r["id_trecho"],
            "nome_via": r["name"] or f"Trecho #{r['id_trecho']}",
            "status": r["classe_risco"],
            "extensao_metros": round(float(r["length"] or 0), 1),
            "score_risco": float(r["ivi_score"] or 0),
            "motivo": f"Vulnerabilidade histórica IVI {r['ivi_score']}"
        }
        for r in trechos_criticos
    ]

    justificativa = rec["motivo"] if rec and rec["motivo"] else (
        f"A rota planejada intercepta {len(pontos_bloqueio)} trecho(s) classificados com severidade de alagamento. Recomendado desvio preventivo para resguardar o veículo e a carga."
        if pontos_bloqueio else "Operação em trechos normais sem restrições severas de alagamento."
    )

    return {
        "id_operacao": op["id_operacao"],
        "tenant_id": op["tenant_id"],
        "id_veiculo": op["id_veiculo"],
        "placa": veiculo["placa"] if veiculo else "N/A",
        "modelo": veiculo["modelo"] if veiculo else "N/A",
        "tipo_veiculo": veiculo["tipo_veiculo"] if veiculo else "N/A",
        "status_operacao": op["status"],
        "acao_recomendada": rec["tipo_acao"] if rec else ("ALTERAR_ROTA" if pontos_bloqueio else "MANTER_ROTA"),
        "nivel_risco": rec["nivel_risco"] if rec else ("CRITICO" if pontos_bloqueio else "NORMAL"),
        "confianca": float(rec["confianca"]) if rec and rec["confianca"] else 0.95,
        "justificativa": justificativa,
        "metricas": {
            "distancia_original_km": dist_orig,
            "distancia_alternativa_km": dist_alt,
            "delta_km": delta_km,
            "tempo_original_min": tempo_orig,
            "tempo_alternativo_min": tempo_alt,
            "delta_tempo_min": delta_tempo,
            "custo_desvio_brl": custo_desvio,
            "prejuizo_evitado_brl": prejuizo_evitado
        },
        "pontos_bloqueio": pontos_bloqueio
    }

@router.get("/exportar-contingencia/csv")
async def exportar_plano_contingencia_csv(tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    query = """
        SELECT 
            o.id_operacao,
            o.tenant_id,
            o.id_veiculo,
            v.placa,
            v.modelo,
            v.tipo_veiculo,
            o.status AS status_operacao,
            COALESCE(r.tipo_acao, 'MANTER_ROTA') AS acao_recomendada,
            COALESCE(r.nivel_risco, 'NORMAL') AS nivel_risco,
            COALESCE(r.confianca, 0.95) AS confianca,
            o.distancia_planejada_km,
            COALESCE(r.km_adicionais, 0.0) AS km_adicionais,
            ROUND((o.distancia_planejada_km + COALESCE(r.km_adicionais, 0.0))::numeric, 2) AS distancia_total_km,
            o.tempo_planejado_min,
            COALESCE(r.minutos_adicionais, 0.0) AS minutos_adicionais,
            ROUND((o.tempo_planejado_min + COALESCE(r.minutos_adicionais, 0.0))::numeric, 2) AS tempo_total_min,
            COALESCE(r.custo_desvio, 0.0) AS custo_desvio_brl,
            COALESCE(r.prejuizo_potencial_evitado, 0.0) AS prejuizo_evitado_brl,
            COALESCE(r.motivo, 'Operação sem impedimentos detectados.') AS justificativa
        FROM operacoes o
        LEFT JOIN veiculos v ON v.id_veiculo = o.id_veiculo AND v.tenant_id = o.tenant_id
        LEFT JOIN LATERAL (
            SELECT tipo_acao, nivel_risco, confianca, km_adicionais, minutos_adicionais, custo_desvio, prejuizo_potencial_evitado, motivo
            FROM recomendacoes_operacao
            WHERE id_operacao = o.id_operacao AND tenant_id = o.tenant_id
            ORDER BY id_recomendacao DESC
            LIMIT 1
        ) r ON true
        WHERE o.tenant_id = $1
        ORDER BY o.id_operacao;
    """
    rows = await conn.fetch(query, tenant_id)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        "TENANT_ID", "ID_OPERACAO", "ID_VEICULO", "PLACA", "MODELO", "TIPO_VEICULO",
        "STATUS", "ACAO_RECOMENDADA", "NIVEL_RISCO", "CONFIANCA",
        "KM_PLANEJADO", "KM_ADICIONAIS", "KM_TOTAL",
        "TEMPO_PLANEJADO_MIN", "MINUTOS_ADICIONAIS", "TEMPO_TOTAL_MIN",
        "CUSTO_DESVIO_BRL", "PREJUIZO_EVITADO_BRL", "JUSTIFICATIVA"
    ])

    for row in rows:
        writer.writerow([
            row["tenant_id"],
            row["id_operacao"],
            row["id_veiculo"],
            row["placa"] or "N/A",
            row["modelo"] or "N/A",
            row["tipo_veiculo"] or "N/A",
            row["status_operacao"],
            row["acao_recomendada"],
            row["nivel_risco"],
            row["confianca"],
            row["distancia_planejada_km"],
            row["km_adicionais"],
            row["distancia_total_km"],
            row["tempo_planejado_min"],
            row["minutos_adicionais"],
            row["tempo_total_min"],
            row["custo_desvio_brl"],
            row["prejuizo_evitado_brl"],
            row["justificativa"]
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=plano_contingencia_{tenant_id}.csv"}
    )

@router.post("/operacoes/importar-lote", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"])), Depends(aplicar_rate_limit)])
async def importar_operacoes_lote(lote: List[Dict[str, Any]], tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    sucessos = 0
    erros = []
    for item in lote:
        try:
            id_op = item.get("id_operacao")
            id_v = item.get("id_veiculo")
            op_tenant = item.get("tenant_id", tenant_id)
            orig_nome = item.get("origem_nome", "Ponto de Coleta")
            orig_lat = float(item["origem_lat"])
            orig_lon = float(item["origem_lon"])
            dest_nome = item.get("destino_nome", "Destinatário")
            dest_lat = float(item["destino_lat"])
            dest_lon = float(item["destino_lon"])
            dist_km = float(item.get("distancia_planejada_km", 5.0))
            tempo_min = float(item.get("tempo_planejado_min", 15.0))
            custo = float(item.get("custo_estimado", round(dist_km * 4.5 + (tempo_min / 60.0) * 85.0, 2)))

            query = """
                INSERT INTO operacoes (
                    id_operacao, id_veiculo, origem_nome, origem_lat, origem_lon,
                    destino_nome, destino_lat, destino_lon, janela_inicio, janela_fim,
                    status, distancia_planejada_km, tempo_planejado_min, custo_estimado, tenant_id
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, NOW(), NOW() + INTERVAL '4 hours',
                    'PLANNED', $9, $10, $11, $12
                )
                ON CONFLICT (id_operacao) DO UPDATE SET
                    id_veiculo = EXCLUDED.id_veiculo,
                    origem_nome = EXCLUDED.origem_nome,
                    origem_lat = EXCLUDED.origem_lat,
                    origem_lon = EXCLUDED.origem_lon,
                    destino_nome = EXCLUDED.destino_nome,
                    destino_lat = EXCLUDED.destino_lat,
                    destino_lon = EXCLUDED.destino_lon,
                    distancia_planejada_km = EXCLUDED.distancia_planejada_km,
                    tempo_planejado_min = EXCLUDED.tempo_planejado_min,
                    custo_estimado = EXCLUDED.custo_estimado,
                    tenant_id = EXCLUDED.tenant_id;
            """
            await conn.execute(query, id_op, id_v, orig_nome, orig_lat, orig_lon, dest_nome, dest_lat, dest_lon, dist_km, tempo_min, custo, op_tenant)
            sucessos += 1
        except Exception as e:
            erros.append({"id_operacao": item.get("id_operacao"), "erro": str(e)})

    return {"total_recebido": len(lote), "tenant_id": tenant_id, "sucessos": sucessos, "falhas": len(erros), "detalhe_falhas": erros}

@router.post("/alertas/disparar-webhook", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"]))])
async def disparar_alerta_webhook(dados: WebhookAlertaRequest, conn: asyncpg.Connection = Depends(get_connection), tenant_autenticado: str = Depends(resolve_tenant)):
    if not is_safe_url(dados.webhook_url):
        raise HTTPException(status_code=400, detail="SSRF bloqueado")
    if dados.tenant_id != tenant_autenticado:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    op = await conn.fetchrow("SELECT * FROM operacoes WHERE id_operacao = $1 AND tenant_id = $2;", dados.id_operacao, dados.tenant_id)
    if not op:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")

    veiculo = await conn.fetchrow("SELECT placa, modelo, tipo_veiculo FROM veiculos WHERE id_veiculo = $1 AND tenant_id = $2;", op["id_veiculo"], dados.tenant_id)
    rec = await conn.fetchrow("""
        SELECT tipo_acao, nivel_risco, motivo, confianca, km_adicionais, minutos_adicionais, custo_desvio, prejuizo_potencial_evitado
        FROM recomendacoes_operacao
        WHERE id_operacao = $1 AND tenant_id = $2
        ORDER BY id_recomendacao DESC LIMIT 1;
    """, dados.id_operacao, dados.tenant_id)

    payload_alerta = {
        "evento": "ALERTA_OPERACAO_CRITICA",
        "tenant_id": dados.tenant_id,
        "timestamp": str(op["criado_em"]),
        "operacao": {
            "id_operacao": op["id_operacao"],
            "status": op["status"],
            "veiculo": {
                "id_veiculo": op["id_veiculo"],
                "placa": veiculo["placa"] if veiculo else "N/A",
                "modelo": veiculo["modelo"] if veiculo else "N/A"
            },
            "recomendacao": {
                "acao": rec["tipo_acao"] if rec else "ALTERAR_ROTA",
                "nivel_risco": rec["nivel_risco"] if rec else "CRITICO",
                "motivo": rec["motivo"] if rec else "Risco de inundação severa no trajeto.",
                "confianca": float(rec["confianca"]) if rec and rec["confianca"] else 0.88
            },
            "impacto_financeiro": {
                "custo_desvio_brl": float(rec["custo_desvio"]) if rec and rec["custo_desvio"] is not None else 0.0,
                "prejuizo_evitado_brl": float(rec["prejuizo_potencial_evitado"]) if rec and rec["prejuizo_potencial_evitado"] is not None else 0.0
            }
        }
    }

    status_envio = "SIMULADO"
    status_code = 200
    try:
        req_data = json.dumps(payload_alerta).encode("utf-8")
        req = urllib.request.Request(
            dados.webhook_url,
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": "SPRain-Resilience-Engine/1.0"},
            method="POST"
        )
        with _opener_seguro.open(req, timeout=4.0) as resp:
            status_code = resp.getcode()
            status_envio = "ENVIADO"
    except Exception as e:
        status_envio = f"FALHA_ENVIO: {str(e)}"
        status_code = 502

    return {
        "sucesso": status_code in [200, 201, 202],
        "status_envio": status_envio,
        "codigo_http": status_code,
        "payload_gerado": payload_alerta
    }

@router.get("/alertas/ativos")
async def listar_alertas_ativos(tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    query = """
        SELECT 
            o.id_operacao,
            o.tenant_id,
            o.id_veiculo,
            v.placa,
            v.modelo,
            r.tipo_acao,
            r.nivel_risco,
            r.motivo,
            r.custo_desvio,
            r.prejuizo_potencial_evitado,
            r.gerado_em
        FROM recomendacoes_operacao r
        JOIN operacoes o ON o.id_operacao = r.id_operacao AND o.tenant_id = r.tenant_id
        LEFT JOIN veiculos v ON v.id_veiculo = o.id_veiculo AND v.tenant_id = o.tenant_id
        WHERE r.tenant_id = $1 AND r.nivel_risco IN ('CRITICO', 'RISCO')
        ORDER BY r.id_recomendacao DESC
        LIMIT 50;
    """
    rows = await conn.fetch(query, tenant_id)
    return [dict(r) for r in rows]

@router.post("/planejamento-d1", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"]))])
async def planejar_operacoes_d1(dados: PlanejamentoD1Request, conn: asyncpg.Connection = Depends(get_connection), tenant_id: str = Depends(resolve_tenant)):
    dados.tenant_id = tenant_id
    from app.services.weather import OpenMeteoProvider
    
    if dados.previsao_chuva_mm <= 0:
        provider = OpenMeteoProvider()
        dados.previsao_chuva_mm = provider.get_forecast_rainfall(-21.79, -48.17, days=1)
        
    query_ops = """
        SELECT o.id_operacao, o.id_veiculo, o.distancia_planejada_km, o.tempo_planejado_min, o.custo_estimado,
               v.placa, v.modelo, v.tipo_veiculo
        FROM operacoes o
        LEFT JOIN veiculos v ON v.id_veiculo = o.id_veiculo AND v.tenant_id = o.tenant_id
        WHERE o.tenant_id = $1
        ORDER BY o.id_operacao;
    """
    ops = await conn.fetch(query_ops, dados.tenant_id)

    operacoes_em_risco = []
    total_desvio_estimado = 0.0
    prejuizo_total_resguardado = 0.0

    for r in ops:
        dist = float(r["distancia_planejada_km"] or 5.0)
        tempo = float(r["tempo_planejado_min"] or 15.0)
        
        exposicao_score = (dados.previsao_chuva_mm * 0.65) * (dist / 10.0) * dados.fator_severidade

        if exposicao_score >= 25.0:
            delta_km = round(dist * 0.35, 2)
            delta_tempo = round(tempo * 0.40, 2)
            custo_desv = round((delta_km * 4.50) + ((delta_tempo / 60.0) * 85.0), 2)
            prejuizo_evitado = 0.0

            total_desvio_estimado += custo_desv
            prejuizo_total_resguardado += prejuizo_evitado

            operacoes_em_risco.append({
                "id_operacao": r["id_operacao"],
                "id_veiculo": r["id_veiculo"],
                "placa": r["placa"] or "N/A",
                "modelo": r["modelo"] or "N/A",
                "exposicao_score": round(exposicao_score, 1),
                "acao_sugerida": "ALTERAR_ROTA_PREVENTIVA" if exposicao_score >= 40.0 else "MONITORAR_JANELA",
                "delta_km_projetado": delta_km,
                "delta_tempo_projetado_min": delta_tempo,
                "custo_desvio_projetado_brl": custo_desv
            })

    return {
        "data_planejamento": dados.data_alvo,
        "tenant_id": dados.tenant_id,
        "previsao_aplicada_mm": dados.previsao_chuva_mm,
        "total_operacoes_analisadas": len(ops),
        "total_operacoes_em_risco": len(operacoes_em_risco),
        "custo_total_desvio_projetado_brl": round(total_desvio_estimado, 2),
        "prejuizo_potencial_preservado_brl": round(prejuizo_total_resguardado, 2),
        "detalhamento_risco": operacoes_em_risco
    }

@router.get("/auditoria/acuracia", dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "VIEWER"]))])
async def obter_auditoria_acuracia(conn: asyncpg.Connection = Depends(get_connection)):
    query = """
        SELECT 
            COUNT(*) AS total_avaliado,
            COUNT(*) FILTER (WHERE resultado_classificacao = 'VERDADEIRO_POSITIVO') AS vp,
            COUNT(*) FILTER (WHERE resultado_classificacao = 'FALSO_POSITIVO') AS fp,
            COUNT(*) FILTER (WHERE resultado_classificacao = 'VERDADEIRO_NEGATIVO') AS vn,
            COUNT(*) FILTER (WHERE resultado_classificacao = 'FALSO_NEGATIVO') AS fn
        FROM auditoria_previsao_realidade;
    """
    row = await conn.fetchrow(query)
    
    if row is None:
        raise HTTPException(status_code=500, detail="Falha ao consultar os dados.")
    total = int(row["total_avaliado"] or 0)
    vp = int(row["vp"] or 0)
    fp = int(row["fp"] or 0)
    vn = int(row["vn"] or 0)
    fn = int(row["fn"] or 0)
    
    base_calc = vp + fp + vn + fn
    if base_calc == 0:
        return {
            "amostra_historica_total": 0,
            "matriz_confusao": {"verdadeiros_positivos": 0, "falsos_positivos": 0, "verdadeiros_negativos": 0, "falsos_negativos": 0},
            "metricas_resiliencia": {"acuracia_global_pct": 0.0, "precisao_alertas_pct": 0.0, "sensibilidade_deteccao_pct": 0.0},
            "status_motor": "SEM_DADOS_SUFICIENTES",
            "aviso": "Auditoria sem registros operacionais reais no banco."
        }
    
    acuracia = round(((vp + vn) / base_calc) * 100.0, 1)
    precisao = round((vp / max(1, vp + fp)) * 100.0, 1)
    sensibilidade = round((vp / max(1, vp + fn)) * 100.0, 1)

    return {
        "amostra_historica_total": base_calc,
        "matriz_confusao": {
            "verdadeiros_positivos": vp,
            "falsos_positivos": fp,
            "verdadeiros_negativos": vn,
            "falsos_negativos": fn
        },
        "metricas_resiliencia": {
            "acuracia_global_pct": acuracia,
            "precisao_alertas_pct": precisao,
            "sensibilidade_deteccao_pct": sensibilidade
        },
        "status_motor": "CALIBRADO_ALTA_CONFIANCA" if acuracia >= 85.0 else "EM_CALIBRACAO"
    }

@router.get("/performance/cache", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"]))])
async def obter_status_cache():
    return RoutingEngine.cache_stats()

@router.post("/performance/cache/limpar", dependencies=[Depends(require_role(["ADMIN"]))])
async def limpar_cache():
    RoutingEngine.clear_cache()
    return {"sucesso": True, "mensagem": "Cache de rotas esvaziado"}



from app.services.observabilidade import MetricsCollector

@router.get("/observabilidade/metricas", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"]))])
async def obter_metricas_sistema():
    return MetricsCollector.obter_metricas()

@router.post("/observabilidade/reset", dependencies=[Depends(require_role(["ADMIN"]))])
async def resetar_metricas_sistema():
    MetricsCollector.resetar()
    return {"sucesso": True, "mensagem": "Metricas de observabilidade zeradas com sucesso"}

import csv
import io
from fastapi.responses import StreamingResponse

@router.get("/relatorios/auditoria.csv", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"]))])
async def exportar_auditoria_csv(tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    query = """
        SELECT 
            COALESCE(o.id_veiculo, 'N/A') AS id_veiculo,
            COALESCE(o.origem_nome, 'Origem') AS origem,
            COALESCE(o.destino_nome, 'Destino') AS destino,
            COALESCE(c.precipitacao_mm, 0.0) AS precipitacao_mm,
            COALESCE(r.nivel_risco, 'NORMAL') AS impacto_detectado,
            COALESCE(r.prejuizo_potencial_evitado, 0.0) AS custo_evitado_reais,
            TO_CHAR(COALESCE(r.gerado_em, o.criado_em), 'YYYY-MM-DD HH24:MI') AS data_registro
        FROM operacoes o
        LEFT JOIN recomendacoes_operacao r ON r.id_operacao = o.id_operacao AND r.tenant_id = o.tenant_id
        LEFT JOIN cenarios_clima c ON c.id_cenario = r.id_cenario
        WHERE o.tenant_id = $1
        ORDER BY o.criado_em DESC
        LIMIT 500;
    """
    rows = await conn.fetch(query, tenant_id)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["id_veiculo", "origem", "destino", "precipitacao_mm", "impacto_detectado", "custo_evitado_reais", "data_registro"])
    
    if not rows:
        writer.writerow(["SEM_DADOS", "Nenhum registro para o tenant informado", "", 0.0, "N/A", 0.0, ""])
    else:
        for r in rows:
            writer.writerow([
                r["id_veiculo"],
                r["origem"],
                r["destino"],
                r["precipitacao_mm"],
                r["impacto_detectado"],
                r["custo_evitado_reais"],
                r["data_registro"]
            ])
            
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=auditoria_logistica_{tenant_id}.csv"}
    )

@router.get("/relatorios/sumario-executivo", dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "VIEWER"]))])
async def obter_sumario_executivo(tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    query = """
        SELECT 
            COUNT(DISTINCT o.id_operacao)::int AS total_operacoes,
            COUNT(DISTINCT r.id_operacao) FILTER (WHERE r.nivel_risco IN ('CRITICO', 'RISCO'))::int AS rotas_em_risco,
            COUNT(DISTINCT r.id_operacao) FILTER (WHERE r.tipo_acao = 'ALTERAR_ROTA')::int AS rotas_recalculadas,
            COALESCE(SUM(r.prejuizo_potencial_evitado), 0.0)::float AS prejuizo_evitado,
            COALESCE(SUM(r.minutos_adicionais), 0.0)::float AS tempo_desvios
        FROM operacoes o
        LEFT JOIN recomendacoes_operacao r ON r.id_operacao = o.id_operacao AND r.tenant_id = o.tenant_id
        WHERE o.tenant_id = $1;
    """
    row = await conn.fetchrow(query, tenant_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Falha ao consultar os dados.")
    total_ops = int(row["total_operacoes"] or 0)
    rotas_risco = int(row["rotas_em_risco"] or 0)
    recalculadas = int(row["rotas_recalculadas"] or 0)
    indice_resiliencia = 100.0 if rotas_risco == 0 else round((recalculadas / max(1, rotas_risco)) * 100.0, 1)

    return {
        "tenant_id": tenant_id,
        "periodo": "D-0 / D+1",
        "kpis": {
            "total_operacoes": total_ops,
            "rotas_em_risco_alagamento": rotas_risco,
            "rotas_recalculadas_com_sucesso": recalculadas,
            "indice_resiliencia_pct": indice_resiliencia,
            "prejuizo_estimado_evitado_brl": round(float(row["prejuizo_evitado"] or 0.0), 2),
            "tempo_total_desvios_min": round(float(row["tempo_desvios"] or 0.0), 1),
            "status_sla": "OPERACAO_PROTEGIDA" if (rotas_risco == 0 or recalculadas == rotas_risco) else "ATENCAO_OPERACIONAL"
        }
    }


from app.services.webhook_dispatcher import WebhookDispatcher
from pydantic import BaseModel

class WebhookConfigRequest(BaseModel):
    url: str
    secret: str
    eventos: list[str]

class WebhookTestRequest(BaseModel):
    evento: str = "ALERTA_ALAGAMENTO"
    dados: dict
    enviar: bool = False


@router.post("/webhooks/configurar", dependencies=[Depends(require_role(["ADMIN"]))])
async def configurar_webhook_tenant(payload: WebhookConfigRequest, tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    if not is_safe_url(payload.url):
        raise HTTPException(status_code=400, detail="SSRF bloqueado")
    return await WebhookDispatcher.configurar_webhook(conn, tenant_id, payload.url, payload.secret, payload.eventos)

@router.post("/webhooks/testar", dependencies=[Depends(require_role(["ADMIN", "OPERATOR"]))])
async def testar_webhook_tenant(payload: WebhookTestRequest, tenant_id: str = Depends(resolve_tenant), conn: asyncpg.Connection = Depends(get_connection)):
    resultado = await WebhookDispatcher.disparar_evento_sincrono(conn, tenant_id, payload.evento, payload.dados)
    if not resultado["sucesso"]:
        raise HTTPException(status_code=400, detail=resultado["motivo"])
    if payload.enviar:
        resultado["envio"] = await WebhookDispatcher.enviar_resultado(resultado)
    return resultado

from app.schemas_economic import DecisaoEconomicaRequest
from app.services.economic_engine import EconomicDecisionEngine

@router.post("/decisao-economica", dependencies=[Depends(aplicar_rate_limit)])
async def tomar_decisao_economica(dados: DecisaoEconomicaRequest, conn: asyncpg.Connection = Depends(get_connection)):
    rota_direta = await RoutingEngine.compute_route(
        conn, dados.origem_lon, dados.origem_lat, dados.destino_lon, dados.destino_lat, profile="FASTEST", rain_mm=0.0
    )
    rota_segura = await RoutingEngine.compute_route(
        conn, dados.origem_lon, dados.origem_lat, dados.destino_lon, dados.destino_lat, profile="SAFEST", rain_mm=dados.precipitacao_mm
    )
    
    if not rota_direta or not rota_segura:
        raise HTTPException(status_code=400, detail="Nao foi possivel rotear os pontos informados sobre a malha viaria.")
        
    fator_chuva = min(1.0, dados.precipitacao_mm / 100.0)
    prob_atraso = round(min(0.95, 0.20 + (fator_chuva * 0.70)), 2)
    prob_bloqueio = round(min(0.90, 0.10 + (fator_chuva * 0.80)), 2)
    
    rota_direta_info = {
        "distancia_km": rota_direta["distancia_km"],
        "tempo_min": rota_direta["tempo_min"],
        "probabilidade_atraso": prob_atraso,
        "probabilidade_bloqueio": prob_bloqueio
    }
    
    rota_segura_info = {
        "distancia_km": rota_segura["distancia_km"],
        "tempo_min": rota_segura["tempo_min"],
        "probabilidade_atraso": 0.08,
        "probabilidade_bloqueio": 0.01
    }
    
    resultado = EconomicDecisionEngine.compare_and_recommend(
        rota_direta=rota_direta_info,
        rota_segura=rota_segura_info,
        parametros=dados.parametros.model_dump()
    )
    
    return {
        "tenant_id": dados.tenant_id,
        "chuva_simulada_mm": dados.precipitacao_mm,
        "decisao": resultado,
        "rotas_geometria": {
            "rota_direta": rota_direta["geojson"],
            "rota_alternativa": rota_segura["geojson"]
        }
    }

@router.get("/central-frota", dependencies=[Depends(aplicar_rate_limit)])
async def obter_painel_central_frota(tenant_id: str = Depends(resolve_tenant), precipitacao_referencia_mm: float = 60.0, conn: asyncpg.Connection = Depends(get_connection)):
    query = """
        SELECT 
            v.id_veiculo,
            v.placa,
            v.modelo,
            v.tipo_veiculo,
            COALESCE(v.lat_atual, -23.542) AS lat_atual,
            COALESCE(v.lon_atual, -46.468) AS lon_atual,
            o.id_operacao,
            o.origem_nome,
            o.destino_nome,
            o.distancia_planejada_km,
            o.tempo_planejado_min,
            o.status AS status_operacao,
            o.janela_fim,
            COUNT(ort.id_trecho) AS total_trechos_rota,
            COUNT(ort.id_trecho) FILTER (WHERE t.classe_risco IN ('Alto', 'Critico')) AS trechos_risco
        FROM veiculos v
        LEFT JOIN operacoes o ON o.id_veiculo = v.id_veiculo AND o.tenant_id = v.tenant_id AND o.status IN ('PLANNED', 'IN_TRANSIT')
        LEFT JOIN operacao_rotas_trechos ort ON ort.id_operacao = o.id_operacao
        LEFT JOIN trechos_osm t ON t.id_trecho = ort.id_trecho
        WHERE v.tenant_id = $1
        GROUP BY v.id_veiculo, v.placa, v.modelo, v.tipo_veiculo, v.lat_atual, v.lon_atual, o.id_operacao, o.origem_nome, o.destino_nome, o.distancia_planejada_km, o.tempo_planejado_min, o.status, o.janela_fim
        ORDER BY v.id_veiculo;
    """
    rows = await conn.fetch(query, tenant_id)
    
    frota = []
    total_veiculos = len(rows)
    veiculos_em_risco = 0
    impacto_financeiro_evitavel_total = 0.0

    for r in rows:
        tem_operacao = r["id_operacao"] is not None
        trechos_risco = int(r["trechos_risco"] or 0)
        
        if not tem_operacao:
            status_frota = "DISPONIVEL"
            nivel_risco = "BAIXO"
            prob_atraso = 0.0
            eta_min = 0.0
            acao = "AGUARDANDO_DESPACHO"
            custo_desvio = 0.0
            economia_estimada = 0.0
        else:
            status_frota = "EM_TRANSITO"
            dist_km = float(r["distancia_planejada_km"] or 8.0)
            tempo_base_min = float(r["tempo_planejado_min"] or 20.0)
            
            fator_chuva = min(1.0, precipitacao_referencia_mm / 100.0)
            score_exposicao = (trechos_risco * 25.0) + (fator_chuva * 40.0)
            
            if score_exposicao >= 60.0 or trechos_risco >= 2:
                nivel_risco = "ALTO"
                prob_atraso = min(0.95, 0.45 + (fator_chuva * 0.50))
                eta_min = round(tempo_base_min * 1.6, 1)
                acao = "ALTERAR_ROTA_IMEDIATO"
                custo_desvio = round(dist_km * 0.35 * 6.50, 2)
                economia_estimada = 2800.00
                veiculos_em_risco += 1
                impacto_financeiro_evitavel_total += economia_estimada
            elif score_exposicao >= 35.0 or trechos_risco == 1:
                nivel_risco = "MEDIO"
                prob_atraso = min(0.70, 0.25 + (fator_chuva * 0.35))
                eta_min = round(tempo_base_min * 1.25, 1)
                acao = "MONITORAR_ALERTA"
                custo_desvio = 0.0
                economia_estimada = 0.0
            else:
                nivel_risco = "BAIXO"
                prob_atraso = 0.05
                eta_min = tempo_base_min
                acao = "MANTER_CURSO"
                custo_desvio = 0.0
                economia_estimada = 0.0

        frota.append({
            "id_veiculo": r["id_veiculo"],
            "placa": r["placa"],
            "modelo": r["modelo"],
            "tipo_veiculo": r["tipo_veiculo"],
            "status_monitoramento": status_frota,
            "operacao_atual": {
                "id_operacao": r["id_operacao"],
                "rota": f"{r['origem_nome']} -> {r['destino_nome']}" if tem_operacao else None,
                "distancia_km": float(r["distancia_planejada_km"]) if tem_operacao and r["distancia_planejada_km"] is not None else None,
                "eta_estimado_min": eta_min
            } if tem_operacao else None,
            "analise_risco": {
                "nivel": nivel_risco,
                "probabilidade_atraso_pct": round(prob_atraso * 100, 1),
                "trechos_vulneraveis_rota": trechos_risco,
                "recomendacao_acao": acao
            },
            "impacto_financeiro_projetado": {
                "custo_desvio_brl": custo_desvio,
                "economia_potencial_brl": economia_estimada
            }
        })

    return {
        "tenant_id": tenant_id,
        "clima_referencia_mm": precipitacao_referencia_mm,
        "sumario_central": {
            "total_frota": total_veiculos,
            "em_operacao": sum(1 for v in frota if v["status_monitoramento"] == "EM_TRANSITO"),
            "veiculos_alto_risco": veiculos_em_risco,
            "taxa_comprometimento_pct": round((veiculos_em_risco / max(1, total_veiculos)) * 100, 1),
            "economia_potencial_total_brl": round(impacto_financeiro_evitavel_total, 2)
        },
        "veiculos": frota
    }

from app.services.weather_alert_engine import SevereWeatherEngine

@router.get("/alertas-meteorologicos", dependencies=[Depends(aplicar_rate_limit)])
async def obter_alertas_meteorologicos_regiao(precipitacao_mm: float = 65.0, rajada_vento_kmh: float = 40.0):
    alerta = SevereWeatherEngine.parse_alert_severity(precipitacao_mm, rajada_vento_kmh)
    return {
        "fonte": "SPRain Unified Weather Feed (CGE/INMET/CEMADEN)",
        "jurisdicao": "Regiao Metropolitana de Sao Paulo - Polo Zona Leste",
        "alerta": alerta
    }

@router.post("/rate-limit/reset", dependencies=[Depends(require_role(["ADMIN"]))])
async def resetar_rate_limit_servidor():
    TenantRateLimiter.reset()
    return {"sucesso": True, "status": "RATE_LIMIT_RESETADO"}
