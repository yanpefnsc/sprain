import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

@pytest.mark.asyncio
async def test_configuracao_webhook_admin():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_admin_demo"}
        payload = {
            "url": "https://example.com/api/alerta",
            "secret": "chave_secreta_integracao_2026",
            "eventos": ["ALERTA_ALAGAMENTO", "ROTA_RECALCULADA"]
        }
        resp = await client.post("/webhooks/configurar?tenant_id=demo_corp", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CONFIGURADO"
        assert data["tenant_id"] == "demo_corp"

@pytest.mark.asyncio
async def test_disparo_webhook_com_assinatura_hmac():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_operator_demo"}
        payload_teste = {
            "evento": "ALERTA_ALAGAMENTO",
            "dados": {
                "id_trecho": 1042,
                "logradouro": "Radial Leste - Viaduto Itaquera",
                "nivel_alagamento": "INTRANSITAVEL",
                "acao_tomada": "DESVIO_AUTOMATICO_ATRIBUIDO"
            }
        }
        resp = await client.post("/webhooks/testar?tenant_id=demo_corp", json=payload_teste, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["sucesso"] is True
        assert "X-SPRain-Signature" in data["headers"]
        assert len(data["headers"]["X-SPRain-Signature"]) == 64

@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x",
    "http://localhost/x",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/x",
    "http://[::1]/x",
    "file:///etc/passwd",
    "ftp://example.com/x",
])
async def test_webhook_bloqueia_ssrf(url):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        payload = {"url": url, "secret": "x", "eventos": ["ALERTA_ALAGAMENTO"]}
        resp = await client.post("/webhooks/configurar?tenant_id=demo_corp", json=payload)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "SSRF bloqueado"
