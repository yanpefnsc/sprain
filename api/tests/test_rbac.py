import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

@pytest.mark.asyncio
async def test_rbac_viewer_bloqueado_na_simulacao():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        headers = {"X-API-Key": "key_viewer_demo"}
        payload = {"precipitacao_mm": 50.0, "tenant_id": "demo_corp"}
        resp = await client.post("/simular-impacto", json=payload, headers=headers)
        assert resp.status_code == 403

@pytest.mark.asyncio
async def test_rbac_admin_autorizado_limpar_cache():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        headers = {"X-API-Key": "key_admin_demo"}
        resp = await client.post("/performance/cache/limpar", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["sucesso"] is True