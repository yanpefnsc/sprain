from app.seguranca import require_role
import csv
import io
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, Response

from app.database import get_connection

router = APIRouter(prefix="/api/v1/relatorios", tags=["Relatorios"])

SQL_OCORRENCIAS = r"""
    SELECT e.id_estado,
           t.name AS logradouro,
           e.status,
           e.severidade,
           COALESCE(substring(e.relato_origem from '^\[([^\]]+)\]'), 'NAO_INFORMADA') AS corporacao,
           e.registrado_em,
           e.relato_origem AS observacao
    FROM estado_operacional_trechos e
    JOIN trechos_osm t ON t.id_trecho = e.id_trecho
    WHERE e.status != 'TRANSITAVEL'
    ORDER BY e.registrado_em DESC;
"""


@router.get("/boletim-defesa-civil/json")
async def gerar_boletim_json(conn: asyncpg.Connection = Depends(get_connection)):
    linhas = await conn.fetch(SQL_OCORRENCIAS)

    stats = await conn.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM estado_operacional_trechos
             WHERE status IN ('INTRANSITAVEL', 'INTRANSITAVEL_LEVES')) AS total_bloqueadas,
            ROUND(AVG(COALESCE(ivi_score, 0))::numeric, 2) AS media_ivi,
            COUNT(*) FILTER (WHERE COALESCE(ivi_score, 0) >= 70) AS total_criticas
        FROM trechos_osm;
    """)

    return {
        "orgao_emissor": "Defesa Civil / SPRAIN Sala de Situacao",
        "jurisdicao": "Distrito de Itaquera - Sao Paulo / SP",
        "data_emissao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sumario_executivo": {
            "vias_interditadas_momento": stats["total_bloqueadas"],
            "vias_risco_critico_ivi": stats["total_criticas"],
            "indice_vulnerabilidade_medio": float(stats["media_ivi"] or 0)
        },
        "detalhamento_vias": [
            {
                "id": r["id_estado"],
                "logradouro": r["logradouro"] or "Sem denominacao",
                "status": r["status"],
                "severidade": r["severidade"],
                "origem": r["corporacao"],
                "horario": r["registrado_em"].strftime("%H:%M:%S") if r["registrado_em"] else "",
                "observacao": r["observacao"]
            }
            for r in linhas
        ]
    }


@router.get("/boletim-defesa-civil/csv")
async def gerar_boletim_csv(conn: asyncpg.Connection = Depends(get_connection)):
    linhas = await conn.fetch(SQL_OCORRENCIAS)

    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=';')
    escritor.writerow(["LOGRADOURO", "STATUS", "SEVERIDADE", "CORPORACAO_ORIGEM", "HORARIO_REGISTRO", "OBSERVACOES"])

    for r in linhas:
        escritor.writerow([
            r["logradouro"] or "Sem denominacao",
            r["status"],
            r["severidade"],
            r["corporacao"],
            r["registrado_em"].strftime("%Y-%m-%d %H:%M:%S") if r["registrado_em"] else "",
            r["observacao"] or ""
        ])

    nome_arquivo = f"boletim_defesa_civil_itaquera_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content="\ufeff" + saida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )
@router.get("/auditoria-intermunicipal", dependencies=[Depends(require_role(["ADMIN", "OPERATOR", "VIEWER"]))])
async def exportar_auditoria_intermunicipal(
    origem: str = "Araraquara",
    destino: str = "Sao Paulo",
    formato: str = "json",
    conn: asyncpg.Connection = Depends(get_connection)
):
    query_dados = """
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
    rows = await conn.fetch(query_dados)
    
    total_km = sum(float(r["distancia_km"]) for r in rows)
    tempo_nominal = sum(float(r["tempo_nominal_min"]) for r in rows)
    tempo_real = sum(float(r["tempo_real_min"]) for r in rows)
    
    trechos_bloqueados = [r for r in rows if r["status_pista"] == "RISCO_CRITICO_ALAGAMENTO"]
    houve_alerta = len(trechos_bloqueados) > 0
    
    adicional_km = 18.4 if houve_alerta else 0.0
    tempo_desvio = (tempo_nominal + 15.0) if houve_alerta else tempo_real
    economia_tempo = (tempo_real - tempo_desvio) if houve_alerta else 0.0
    
    custo_diesel_extra = adicional_km * (6.10 / 2.5)
    economia_hora_parada = economia_tempo * (150.0 / 60.0)
    beneficio_liquido = economia_hora_parada - custo_diesel_extra
    
    dados_sumario = {
        "rota": f"{origem} -> {destino}",
        "distancia_nominal_km": round(total_km, 1),
        "tempo_nominal_min": round(tempo_nominal, 1),
        "tempo_estimado_sem_desvio_min": round(tempo_real, 1),
        "tempo_com_desvio_min": round(tempo_desvio, 1),
        "economia_tempo_min": round(economia_tempo, 1),
        "custo_diesel_extra_brl": round(custo_diesel_extra, 2),
        "economia_hora_parada_brl": round(economia_hora_parada, 2),
        "beneficio_liquido_brl": round(beneficio_liquido, 2),
        "status_operacional": "DESVIO_EXECUTADO" if houve_alerta else "ROTA_NORMAL"
    }
    
    if formato.lower() == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=dados_sumario.keys())
        writer.writeheader()
        writer.writerow(dados_sumario)
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sumario_auditoria_intermunicipal.csv"})
        
    return dados_sumario