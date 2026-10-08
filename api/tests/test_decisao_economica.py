import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(45.0, connect=10.0)

@pytest.mark.asyncio
async def test_decisao_economica_tradeoff():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        payload = {
            "tenant_id": "demo_corp",
            "origem_lat": -23.542,
            "origem_lon": -46.468,
            "destino_lat": -23.535,
            "destino_lon": -46.452,
            "precipitacao_mm": 80.0,
            "parametros": {
                "consumo_km_l": 2.8,
                "preco_diesel_litro": 6.30,
                "custo_hora_veiculo": 60.0,
                "custo_hora_motorista": 40.0,
                "valor_frete": 850.0,
                "valor_carga": 50000.0,
                "multa_por_hora_atraso": 200.0,
                "janela_limite_min": 25.0
            }
        }
        resp = await client.post("/decisao-economica", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "decisao" in data
        assert data["decisao"]["recomendacao"] in ["ROTA_ALTERNATIVA_SEGURA", "ROTA_DIRETA_ORIGINAL"]
        assert "tradeoff" in data["decisao"]
        assert "vantagem_economica_brl" in data["decisao"]["tradeoff"]
        assert "rota_direta" in data["rotas_geometria"]
        assert "rota_alternativa" in data["rotas_geometria"]