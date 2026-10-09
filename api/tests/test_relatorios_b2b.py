import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1/logistica"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

@pytest.mark.asyncio
async def test_exportacao_csv_auditoria():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_admin_demo"}
        resp = await client.get("/relatorios/auditoria.csv?tenant_id=demo_corp", headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment; filename=auditoria_logistica_demo_corp.csv" in resp.headers.get("content-disposition", "")
        content = resp.text
        assert "id_veiculo;origem;destino;precipitacao_mm" in content

@pytest.mark.asyncio
async def test_relatorio_sumario_executivo_acesso_viewer():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, headers={"X-API-Key": "key_admin_demo"}) as client:
        headers = {"X-API-Key": "key_viewer_demo"}
        resp = await client.get("/relatorios/sumario-executivo?tenant_id=demo_corp", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "demo_corp"
        assert "kpis" in data
        assert "total_operacoes" in data["kpis"]
        assert "indice_resiliencia_pct" in data["kpis"]