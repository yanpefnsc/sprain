import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/rotas"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
HEADERS_ADMIN = {"X-API-Key": "key_admin_demo"}

@pytest.mark.asyncio
async def test_calculo_rota_intermunicipal_condicoes_favoraveis():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/intermunicipal", headers=HEADERS_ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert data["modalidade"] == "ROTEAMENTO_PREDITIVO_COM_DECISAO_ECONOMICA"
        assert data["resumo"]["distancia_total_km"] == 245.0
        assert data["resumo"]["status_geral"] in ["CONDICOES_FAVORAVEIS", "ALERTA_CLIMATICO"]
        assert "decisao_logistica" in data