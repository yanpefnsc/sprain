import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/health"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

@pytest.mark.asyncio
async def test_owasp_security_headers_presentes():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        resp = await client.get("/liveness")
        assert resp.status_code == 200
        headers = resp.headers
        
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert "max-age=31536000" in headers.get("strict-transport-security", "")
        assert headers.get("referrer-policy") == "no-referrer"
        assert headers.get("x-xss-protection") == "0"
        assert "geolocation=()" in headers.get("permissions-policy", "")
