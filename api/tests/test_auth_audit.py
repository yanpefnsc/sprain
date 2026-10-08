import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

@pytest.mark.asyncio
async def test_rejeita_requisicao_sem_api_key():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/veiculos")
        assert resp.status_code == 401

@pytest.mark.asyncio
async def test_rejeita_cadastro_veiculo_sem_autenticacao():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        payload = {
            "id_veiculo": "HACK_01",
            "placa": "HCK0001",
            "modelo": "Truck",
            "tipo_veiculo": "VUC"
        }
        resp = await client.post("/veiculos", json=payload)
        assert resp.status_code == 401