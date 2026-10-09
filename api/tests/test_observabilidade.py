import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

@pytest.mark.asyncio
async def test_middleware_injeta_header_process_time():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_admin_demo"}
        resp = await client.get("/veiculos?tenant_id=demo_corp", headers=headers)
        assert resp.status_code == 200
        assert "x-process-time-ms" in resp.headers
        latencia = float(resp.headers["x-process-time-ms"])
        assert latencia >= 0.0

@pytest.mark.asyncio
async def test_endpoint_metricas_observabilidade():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_admin_demo"}
        resp = await client.get("/observabilidade/metricas", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_monitor"] == "OPERACIONAL"
        assert data["total_requisicoes"] > 0
        assert "latencia_media_global_ms" in data
        assert "detalhamento_por_rota" in data

@pytest.mark.asyncio
async def test_bloqueio_viewer_reset_metricas():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_viewer_demo"}
        resp = await client.post("/observabilidade/reset", headers=headers)
        assert resp.status_code == 403