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