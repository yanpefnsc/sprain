import os
import requests
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

COORDENADAS_SEGMENTOS = {
    1: {"nome": "Araraquara/Sao Carlos", "lat": -21.90, "lon": -48.03},
    2: {"nome": "Sao Carlos/Rio Claro", "lat": -22.21, "lon": -47.72},
    3: {"nome": "Rio Claro/Limeira", "lat": -22.48, "lon": -47.48},
    4: {"nome": "Limeira/Campinas", "lat": -22.73, "lon": -47.23},
    5: {"nome": "Campinas/Jundiai", "lat": -23.04, "lon": -46.97},
    6: {"nome": "Jundiai/Sao Paulo", "lat": -23.35, "lon": -46.80}
}

def consultar_precipitacao(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=precipitation,rain&timezone=America%2FSao_Paulo"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            dados = resp.json().get("current", {})
            return float(dados.get("precipitation", 0.0))
    except Exception as e:
        print(f"Aviso: Falha ao consultar coordenadas ({lat}, {lon}): {e}")
    return 0.0

def calcular_impacto(precipitacao_mm_h):
    if precipitacao_mm_h >= 50.0:
        return "RISCO_CRITICO_ALAGAMENTO", 2.5
    elif precipitacao_mm_h >= 25.0:
        return "ALERTA_MODERADO", 1.5
    elif precipitacao_mm_h >= 5.0:
        return "PISTA_MOLHADA", 1.15
    return "LIBERADA", 1.0

def main():
    motor = create_engine(URL_BANCO)
    print("Iniciando telemetria meteorologica para o corredor SP-310 / SP-348...")
    
    with motor.begin() as conn:
        for id_trecho, dados in COORDENADAS_SEGMENTOS.items():
            chuva = consultar_precipitacao(dados["lat"], dados["lon"])
            status, fator = calcular_impacto(chuva)
            
            stmt = text("""
                INSERT INTO condicoes_corredor (id_trecho, status_pista, precipitacao_mm_h, fator_atraso, atualizado_em)
                VALUES (:id, :status, :chuva, :fator, NOW())
                ON CONFLICT (id_trecho) DO UPDATE 
                SET status_pista = EXCLUDED.status_pista,
                    precipitacao_mm_h = EXCLUDED.precipitacao_mm_h,
                    fator_atraso = EXCLUDED.fator_atraso,
                    atualizado_em = NOW();
            """)
            conn.execute(stmt, {"id": id_trecho, "status": status, "chuva": chuva, "fator": fator})
            print(f"Segmento {id_trecho} ({dados['nome']}): {chuva:.1f} mm/h -> Status: {status} (Atraso: {fator}x)")

    print("Telemetria do corredor atualizada com sucesso no PostGIS.")

if __name__ == "__main__":
    main()