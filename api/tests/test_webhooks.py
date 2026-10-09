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


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x",
    "http://localhost/x",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/x",
    "file:///etc/passwd",
])
async def test_alerta_webhook_bloqueia_ssrf(url):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_operator_demo"}) as client:
        payload = {"webhook_url": url, "id_operacao": "qualquer", "tenant_id": "demo_corp"}
        resp = await client.post("/alertas/disparar-webhook", json=payload)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "SSRF bloqueado"


@pytest.mark.asyncio
async def test_alerta_webhook_bloqueia_outro_tenant():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_operator_demo"}) as client:
        payload = {"webhook_url": "https://example.com/x", "id_operacao": "qualquer", "tenant_id": "outro_tenant"}
        resp = await client.post("/alertas/disparar-webhook", json=payload)
        assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("metodo,rota", [
    ("GET", "/auditoria/acuracia"),
    ("GET", "/performance/cache"),
    ("POST", "/performance/cache/limpar"),
])
async def test_rotas_internas_exigem_api_key(metodo, rota):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.request(metodo, rota)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_limpar_cache_so_admin():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        negado = await client.post("/performance/cache/limpar", headers={"X-API-Key": "key_operator_demo"})
        assert negado.status_code == 403
        liberado = await client.post("/performance/cache/limpar", headers={"X-API-Key": "key_admin_demo"})
        assert liberado.status_code == 200


@pytest.mark.asyncio
async def test_isolamento_entre_tenants_veiculos():
    corpo = {
        "tenant_id": "log_express",
        "id_veiculo": "VEIC-ISOLAMENTO-01",
        "placa": "ISO1A23",
        "modelo": "Teste",
    }
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        criado = await client.post("/veiculos", json=corpo, headers={"X-API-Key": "key_admin_demo"})
        assert criado.status_code == 200
        assert criado.json()["tenant_id"] == "demo_corp"

        lista_express = await client.get("/veiculos", headers={"X-API-Key": "key_admin_express"})
        assert lista_express.status_code == 200
        ids = [v["id_veiculo"] for v in lista_express.json()]
        assert "VEIC-ISOLAMENTO-01" not in ids

        lista_demo = await client.get("/veiculos", headers={"X-API-Key": "key_admin_demo"})
        ids_demo = [v["id_veiculo"] for v in lista_demo.json()]
        assert "VEIC-ISOLAMENTO-01" in ids_demo


@pytest.mark.asyncio
async def test_webhook_nao_vaza_entre_tenants():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.post("/webhooks/testar", json={"evento": "ALERTA_ALAGAMENTO", "dados": {}}, headers={"X-API-Key": "key_admin_express"})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "WEBHOOK_NAO_CONFIGURADO"
