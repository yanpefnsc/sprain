from fastapi import APIRouter, Depends, Response
import asyncpg
from datetime import datetime
import csv
import io
from app.database import get_connection

router = APIRouter(prefix="/api/v1/relatorios", tags=["Relatórios"])

@router.get("/boletim-defesa-civil/json")
async def gerar_boletim_json(conn: asyncpg.Connection = Depends(get_connection)):
    query_ocorrencias = """
        SELECT o.id_ocorrencia, t.name AS logradouro, o.status, o.severidade, 
               o.corporacao, o.registrado_em, o.observacao
        FROM ocorrencias_ativas o
        JOIN trechos_osm t ON o.id_trecho = t.id_trecho
        ORDER BY o.registrado_em DESC;
    """
    linhas = await conn.fetch(query_ocorrencias)
    
    query_stats = """
        SELECT 
            COUNT(*) FILTER (WHERE status_operacional != 'TRANSITAVEL') AS total_bloqueadas,
            ROUND(AVG(COALESCE(ivi, 0))::numeric, 2) AS media_ivi,
            COUNT(*) FILTER (WHERE COALESCE(ivi, 0) >= 70) AS total_criticas
        FROM trechos_osm;
    """
    stats = await conn.fetchrow(query_stats)
    
    return {
        "orgao_emissor": "Defesa Civil / SPRAIN Sala de Situação",
        "jurisdicao": "Distrito de Itaquera - São Paulo / SP",
        "data_emissao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sumario_executivo": {
            "vias_interditadas_momento": stats["total_bloqueadas"],
            "vias_risco_critico_ivi": stats["total_criticas"],
            "indice_vulnerabilidade_medio": float(stats["media_ivi"] or 0)
        },
        "detalhamento_vias": [
            {
                "id": r["id_ocorrencia"],
                "logradouro": r["logradouro"] or "Sem denominação",
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
    query = """
        SELECT t.name AS logradouro, o.status, o.severidade, 
               o.corporacao, o.registrado_em, o.observacao
        FROM ocorrencias_ativas o
        JOIN trechos_osm t ON o.id_trecho = t.id_trecho
        ORDER BY o.registrado_em DESC;
    """
    linhas = await conn.fetch(query)
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["LOGRADOURO", "STATUS", "SEVERIDADE", "CORPORACAO_ORIGEM", "HORARIO_REGISTRO", "OBSERVACOES"])
    
    for r in linhas:
        writer.writerow([
            r["logradouro"] or "Sem denominação",
            r["status"],
            r["severidade"],
            r["corporacao"],
            r["registrado_em"].strftime("%Y-%m-%d %H:%M:%S") if r["registrado_em"] else "",
            r["observacao"] or ""
        ])
    
    output.seek(0)
    nome_arquivo = f"boletim_defesa_civil_itaquera_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )
