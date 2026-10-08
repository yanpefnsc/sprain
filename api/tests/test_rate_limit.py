import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

@pytest.mark.asyncio
async def test_rate_limit_permite_dentro_da_cota():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/veiculos?tenant_id=demo_corp")
        assert resp.status_code == 200

@pytest.mark.asyncio
async def test_rate_limit_bloqueia_excesso_429():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        tenant_teste = "test_limited"
        status_codes = []
        for _ in range(5):
            resp = await client.get(f"/veiculos?tenant_id={tenant_teste}")
            status_codes.append(resp.status_code)
            
        assert 200 in status_codes
        assert 429 in status_codes
        
        idx_429 = status_codes.index(429)
        assert idx_429 == 3
