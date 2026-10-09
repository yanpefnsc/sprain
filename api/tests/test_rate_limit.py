import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
HEADERS_ADMIN = {"X-API-Key": "key_admin_demo"}

@pytest.mark.asyncio
async def test_rate_limit_permite_dentro_da_cota():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        await client.post("/rate-limit/reset", headers=HEADERS_ADMIN)
        resp = await client.get("/veiculos?tenant_id=demo_corp", headers=HEADERS_ADMIN)
        assert resp.status_code == 200

@pytest.mark.asyncio
async def test_rate_limit_bloqueia_excesso_429():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        try:
            await client.post("/rate-limit/reset", headers=HEADERS_ADMIN)
            status_codes = []
            for _ in range(61):
                resp = await client.get("/veiculos", headers=HEADERS_ADMIN)
                status_codes.append(resp.status_code)
            assert status_codes[:60].count(200) == 60
            assert status_codes[60] == 429
            assert "retry-after" in resp.headers
        finally:
            await client.post("/rate-limit/reset", headers=HEADERS_ADMIN)
