import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

@pytest.mark.asyncio
async def test_painel_central_frota():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/central-frota?tenant_id=demo_corp&precipitacao_referencia_mm=75.0")
        assert resp.status_code == 200
        data = resp.json()
        assert "sumario_central" in data
        assert "veiculos" in data
        assert data["sumario_central"]["total_frota"] >= 0
        assert "economia_potencial_total_brl" in data["sumario_central"]