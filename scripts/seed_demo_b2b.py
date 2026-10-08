import os
import random
import json
import urllib.request
import asyncpg
import asyncio
from datetime import datetime, timedelta

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/v1/logistica")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "enchentes")
DB_PASS = os.getenv("DB_PASSWORD", "enchentes")
DB_NAME = os.getenv("DB_NAME", "enchentes")

def post_json(endpoint, data):
    url = f"{API_URL}/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status

async def obter_pontos_validos():
    conn = await asyncpg.connect(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    rows = await conn.fetch("""
        SELECT 
            ST_Y(ST_Centroid(ST_Transform(geom, 4326))) AS lat,
            ST_X(ST_Centroid(ST_Transform(geom, 4326))) AS lon,
            COALESCE(name, 'Via Logística') AS nome
        FROM trechos_osm 
        WHERE source IS NOT NULL AND target IS NOT NULL
        ORDER BY RANDOM() 
        LIMIT 300;
    """)
    await conn.close()
    return [(float(r["lat"]), float(r["lon"]), r["nome"]) for r in rows]

def main():
    print("Cadastrando 50 veiculos...")
    tipos = ["VUC", "TOCO", "VAN", "CARRETA"]
    for i in range(1, 51):
        v_id = f"TRK-{i:03d}"
        payload = {
            "id_veiculo": v_id,
            "placa": f"BRA{i:02d}9{i%10}",
            "modelo": f"Mercedes Accelo {i%5 + 8}15",
            "tipo_veiculo": random.choice(tipos),
            "lat_atual": -23.542,
            "lon_atual": -46.468
        }
        try:
            post_json("veiculos", payload)
        except Exception:
            pass

    print("Obtendo coordenadas de trechos conectados da malha viaria...")
    pontos = asyncio.run(obter_pontos_validos())
    
    if len(pontos) < 2:
        print("Erro: Malha viaria vazia ou sem conexoes pgr.")
        return

    print("Gerando operacoes logicas...")
    agora = datetime.utcnow()
    sucessos = 0

    for i in range(len(pontos) - 1):
        if sucessos >= 100:
            break

        orig_lat, orig_lon, orig_nome = pontos[i]
        dest_lat, dest_lon, dest_nome = pontos[i + 1]

        op_id = f"OP-{sucessos + 1:03d}"
        v_id = f"TRK-{random.randint(1, 50):03d}"

        payload_op = {
            "id_operacao": op_id,
            "id_veiculo": v_id,
            "origem_nome": f"Origem {orig_nome}",
            "origem_lat": round(orig_lat, 6),
            "origem_lon": round(orig_lon, 6),
            "destino_nome": f"Destino {dest_nome}",
            "destino_lat": round(dest_lat, 6),
            "destino_lon": round(dest_lon, 6),
            "janela_inicio": (agora + timedelta(hours=1)).isoformat(),
            "janela_fim": (agora + timedelta(hours=5)).isoformat()
        }

        try:
            status = post_json("operacoes", payload_op)
            if status == 200:
                sucessos += 1
                if sucessos % 20 == 0:
                    print(f"-> {sucessos} operacoes roteadas e salvas no banco...")
        except Exception:
            pass

    print(f"Cenario concluido: {sucessos} operacoes criadas com sucesso.")

if __name__ == "__main__":
    main()
