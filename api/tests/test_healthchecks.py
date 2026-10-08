import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/health"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

@pytest.mark.asyncio
async def test_health_liveness():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/liveness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"
        assert data["servico"] == "sprain_api"

@pytest.mark.asyncio
async def test_health_readiness_postgis():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "READY"
        assert data["postgis"] == "OPERACIONAL"
        assert data["total_trechos_osm"] > 0
        assert data["latencia_db_ms"] >= 0.0
