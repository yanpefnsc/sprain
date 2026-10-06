import sys
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_connection

caminho_raiz = Path(__file__).resolve().parents[3]
if str(caminho_raiz) not in sys.path:
    sys.path.insert(0, str(caminho_raiz))
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

try:
    from scripts.monitorar_chuva_cge import obter_dados_chuva_itaquera
except ImportError:
    obter_dados_chuva_itaquera = None

router = APIRouter(prefix="/api/v1/monitoramento", tags=["Monitoramento"])
POSTO_ITAQUERA_ID = "1000864"

async def aplicar_impacto_chuva(conn, acumulado_mm: float) -> int:
    query = """
        INSERT INTO estado_operacional_trechos (id_trecho, status, severidade, relato_origem, registrado_em)
        SELECT 
            t.id_trecho,
            CASE 
                -- Bloqueio total restrito a fundos de vale e talvegues criticos
                WHEN ($1 >= 80.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 80.0 AND COALESCE(t.ivi_score, 0.0) >= 75.0) THEN 'INTRANSITAVEL'
                WHEN ($1 >= 50.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 45.0 AND COALESCE(t.ivi_score, 0.0) >= 82.0) THEN 'INTRANSITAVEL'
                WHEN ($1 >= 100.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 120.0 AND COALESCE(t.ivi_score, 0.0) >= 70.0) THEN 'INTRANSITAVEL'
                
                -- Alerta e transito lento para vias em planicie de inundacao
                WHEN ($1 >= 60.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 180.0 AND COALESCE(t.ivi_score, 0.0) >= 60.0) THEN 'INTRANSITAVEL_LEVES'
                WHEN ($1 >= 30.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 80.0 AND COALESCE(t.ivi_score, 0.0) >= 68.0) THEN 'INTRANSITAVEL_LEVES'
                ELSE 'TRANSITAVEL'
            END AS status,
            CASE 
                WHEN ($1 >= 80.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 80.0 AND COALESCE(t.ivi_score, 0.0) >= 75.0) THEN 'VERMELHO'
                WHEN ($1 >= 50.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 45.0 AND COALESCE(t.ivi_score, 0.0) >= 82.0) THEN 'VERMELHO'
                WHEN ($1 >= 100.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 120.0 AND COALESCE(t.ivi_score, 0.0) >= 70.0) THEN 'VERMELHO'
                WHEN ($1 >= 60.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 180.0 AND COALESCE(t.ivi_score, 0.0) >= 60.0) THEN 'LARANJA'
                WHEN ($1 >= 30.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 80.0 AND COALESCE(t.ivi_score, 0.0) >= 68.0) THEN 'LARANJA'
                WHEN ($1 >= 20.0 AND COALESCE(t.distancia_agua_m, 999.0) <= 250.0 AND COALESCE(t.ivi_score, 0.0) >= 50.0) THEN 'AMARELO'
                ELSE 'VERDE'
            END AS severidade,
            CONCAT('Simulacao hidrologica: precipitacao projetada de ', $1, ' mm'),
            NOW()
        FROM trechos_osm t
        ON CONFLICT (id_trecho) DO UPDATE SET
            status = EXCLUDED.status,
            severidade = EXCLUDED.severidade,
            relato_origem = EXCLUDED.relato_origem,
            registrado_em = EXCLUDED.registrado_em;
    """
    status = await conn.execute(query, acumulado_mm)
    partes = status.split(" ")
    return int(partes[-1]) if len(partes) > 1 and partes[-1].isdigit() else 0

@router.post("/simular-chuva")
async def simular_chuva(acumulado_mm: float, conn=Depends(get_connection)):
    linhas = await aplicar_impacto_chuva(conn, acumulado_mm)
    return {
        "status": "sucesso",
        "acumulado_mm": acumulado_mm,
        "trechos_atualizados": linhas
    }

@router.post("/sincronizar-cge")
async def sincronizar_cge(conn=Depends(get_connection)):
    if not obter_dados_chuva_itaquera:
        raise HTTPException(status_code=500, detail="Modulo scripts.monitorar_chuva_cge nao localizado")
    try:
        dados = obter_dados_chuva_itaquera()
        acumulado = float(dados.get("acumulado_mm", 0.0)) if dados else 0.0
        linhas = await aplicar_impacto_chuva(conn, acumulado)
        return {
            "status": "sucesso",
            "telemetria": {
                "posto_id": POSTO_ITAQUERA_ID,
                "acumulado_mm": acumulado,
                "timestamp": datetime.utcnow().isoformat()
            },
            "trechos_atualizados": linhas
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
