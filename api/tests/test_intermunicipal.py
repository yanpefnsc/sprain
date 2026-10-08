import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/rotas"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
HEADERS_ADMIN = {"X-API-Key": "key_admin_demo"}

@pytest.mark.asyncio
async def test_calculo_rota_intermunicipal_araraquara_sp():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/intermunicipal", headers=HEADERS_ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert data["modalidade"] == "ROTEAMENTO_HIERARQUICO_INTERMUNICIPAL"
        assert data["resumo"]["distancia_total_km"] > 200.0
        assert len(data["segmentos_macro"]) == 6