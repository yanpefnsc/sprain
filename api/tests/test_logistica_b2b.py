import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
HEADERS_ADMIN = {"X-API-Key": "key_admin_demo"}

@pytest.mark.asyncio
async def test_cadastro_e_isolamento_multitenant():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        payload_tenant_a = {
            "id_veiculo": "TEST_V_TENANT_A",
            "placa": "TTA0001",
            "modelo": "Van Cargo",
            "tipo_veiculo": "VAN",
            "lat_atual": -23.54,
            "lon_atual": -46.46,
            "tenant_id": "demo_corp"
        }
        resp_cad = await client.post("/veiculos", json=payload_tenant_a, headers=HEADERS_ADMIN)
        assert resp_cad.status_code == 200
        assert resp_cad.json()["sucesso"] is True
        assert resp_cad.json()["tenant_id"] == "demo_corp"

        resp_list_a = await client.get("/veiculos?tenant_id=demo_corp", headers=HEADERS_ADMIN)
        assert resp_list_a.status_code == 200
        veiculos_a = resp_list_a.json()
        assert any(v["id_veiculo"] == "TEST_V_TENANT_A" for v in veiculos_a)

@pytest.mark.asyncio
async def test_simulacao_impacto_b2b():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        payload_sim = {
            "precipitacao_mm": 75.0,
            "tenant_id": "demo_corp"
        }
        resp = await client.post("/simular-impacto", json=payload_sim, headers=HEADERS_ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert "id_cenario" in data
        assert data["clima_simulado_mm"] == 75.0
        assert "resumo_operacional" in data
        assert "recomendacoes" in data

@pytest.mark.asyncio
async def test_planejamento_d1():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        payload_d1 = {
            "data_alvo": "2026-10-10",
            "previsao_chuva_mm": 60.0,
            "fator_severidade": 1.2,
            "tenant_id": "demo_corp"
        }
        resp = await client.post("/planejamento-d1", json=payload_d1, headers=HEADERS_ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_planejamento"] == "2026-10-10"
        assert "total_operacoes_analisadas" in data
        assert "custo_total_desvio_projetado_brl" in data

@pytest.mark.asyncio
async def test_auditoria_acuracia():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/auditoria/acuracia", headers=HEADERS_ADMIN)
        assert resp.status_code == 200
        data = resp.json()
        assert "matriz_confusao" in data
        assert "metricas_resiliencia" in data
        assert "status_motor" in data