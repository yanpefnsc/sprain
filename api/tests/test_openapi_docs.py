import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

@pytest.mark.asyncio
async def test_swagger_ui_acessivel():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/docs")
        assert resp.status_code == 200
        assert "swagger-ui" in resp.text.lower()

@pytest.mark.asyncio
async def test_esquema_openapi_e_tags_corporativas():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["info"]["title"] == "SPRain B2B - Climate Resilience & Logistics Intelligence API"
        assert data["info"]["version"] == "1.0.0"
        assert "openapi" in data
        
        tag_names = [t["name"] for t in data.get("tags", [])]
        assert "Logística & Roteamento Resiliente" in tag_names
        assert "Healthchecks & Infraestrutura" in tag_names
