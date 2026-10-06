import re
import urllib.request
import os
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")
URL_ESTACAO_ITAQUERA = "https://www.cgesp.org/v3/estacao.jsp?POSTO=1000864"

def coletar_chuva_cge() -> dict:
    req = urllib.request.Request(
        URL_ESTACAO_ITAQUERA,
        headers={"User-Agent": "sprain-telemetria/1.0 (pesquisa e monitoramento)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Limpa tags html para facilitar a extração do texto puro
    texto_limpo = re.sub(r'<[^>]+>', ' ', html)
    texto_limpo = re.sub(r'\s+', ' ', texto_limpo)

    m_atual = re.search(r'Per[íi\.]*\s*Atual[:\s]+([\d\.,]+)\s*mm', texto_limpo, re.I)
    m_anterior = re.search(r'Per[íi\.]*\s*Anterior[:\s]+([\d\.,]+)\s*mm', texto_limpo, re.I)

    chuva_atual = float(m_atual.group(1).replace(",", ".")) if m_atual else 0.0
    chuva_anterior = float(m_anterior.group(1).replace(",", ".")) if m_anterior else 0.0

    return {
        "posto": "1000864",
        "nome": "Itaquera - CGE SP",
        "chuva_periodo_atual_mm": chuva_atual,
        "chuva_periodo_anterior_mm": chuva_anterior,
        "chuva_acumulada_recente_mm": round(chuva_atual + chuva_anterior, 1)
    }

def atualizar_risco_por_chuva(dados_chuva: dict):
    mm_total = dados_chuva["chuva_acumulada_recente_mm"]
    motor = create_engine(URL_BANCO)

    # Se não houver chuva acumulada (> 0.5 mm), não altera nada na malha
    if mm_total < 0.5:
        return {
            "chuva_mm": mm_total,
            "limiar_ivi_ativado": None,
            "trechos_em_alerta_ou_bloqueio": 0,
            "status": "Sem chuva relevante no momento."
        }

    # Limiar dinâmico proporcional à chuva acumulada
    limiar_ivi = max(40.0, 85.0 - (mm_total * 1.5))
    relato = f"[Telemetria CGE Itaquera] Chuva recente: {mm_total} mm (Per. Atual: {dados_chuva['chuva_periodo_atual_mm']} mm, Ant: {dados_chuva['chuva_periodo_anterior_mm']} mm)"

    query = text("""
        WITH vias_afetadas AS (
            SELECT id_trecho, CAST(COALESCE(ivi_score, 0) AS float8) AS valor_ivi
            FROM trechos_osm
            WHERE CAST(COALESCE(ivi_score, 0) AS float8) >= :limiar
        )
        INSERT INTO estado_operacional_trechos (id_trecho, status, severidade, relato_origem, registrado_em)
        SELECT 
            id_trecho,
            CASE 
                WHEN valor_ivi >= 75.0 THEN 'INTRANSITAVEL'
                ELSE 'TRANSITAVEL_ALERTA'
            END,
            CASE 
                WHEN valor_ivi >= 75.0 THEN 'VERMELHO'
                ELSE 'AMARELO'
            END,
            :relato,
            NOW()
        FROM vias_afetadas
        ON CONFLICT (id_trecho) DO UPDATE
        SET status = EXCLUDED.status,
            severidade = EXCLUDED.severidade,
            relato_origem = EXCLUDED.relato_origem,
            registrado_em = NOW()
        RETURNING id_trecho;
    """)

    with motor.begin() as conn:
        res = conn.execute(query, {"limiar": limiar_ivi, "relato": relato})
        total_atualizados = len(res.fetchall())

    return {
        "chuva_mm": mm_total,
        "limiar_ivi_ativado": round(limiar_ivi, 1),
        "trechos_em_alerta_ou_bloqueio": total_atualizados,
        "status": "Atualizado com sucesso."
    }

def main():
    print("1. Conectando à estação meteorológica do CGE em Itaquera...")
    dados = coletar_chuva_cge()
    print(f"   -> Posto: {dados['nome']}")
    print(f"   -> Chuva Período Atual: {dados['chuva_periodo_atual_mm']} mm")
    print(f"   -> Chuva Período Anterior: {dados['chuva_periodo_anterior_mm']} mm")
    print(f"   -> Acumulado Recente: {dados['chuva_acumulada_recente_mm']} mm")

    print("\n2. Processando impacto na malha viária...")
    res = atualizar_risco_por_chuva(dados)
    if res["limiar_ivi_ativado"]:
        print(f"   -> Limiar IVI ativado: >= {res['limiar_ivi_ativado']}")
        print(f"   -> Trechos viários sensibilizados: {res['trechos_em_alerta_ou_bloqueio']}")
    else:
        print(f"   -> {res['status']}")

if __name__ == "__main__":
    main()
