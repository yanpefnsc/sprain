import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.database import get_connection
from app.main import app
from app.services import manifesto_service

FUSO_SP = ZoneInfo("America/Sao_Paulo")
AGORA_TESTE = datetime(2026, 10, 21, 10, 0, tzinfo=FUSO_SP)


class Record(dict):
    def __getitem__(self, item):
        return super().__getitem__(item)


class BancoMemoriaManifesto:
    def __init__(self):
        self.veiculos: Dict[Tuple[str, str], dict] = {}
        self.operacoes: Dict[str, dict] = {}
        self.em_transacao: bool = False
        self.transacoes_feitas: int = 0
        self.falhar_na_gravacao: bool = False
        self._backup_estado: Optional[Tuple[dict, dict]] = None

    def transaction(self):
        return TransacaoCtx(self)

    async def fetch(self, query: str, *args):
        if "operacoes o" in query and "veiculos v" in query:
            tenant_id = args[0]
            resultado = []
            for op in self.operacoes.values():
                if op["tenant_id"] == tenant_id:
                    v = self.veiculos.get((tenant_id, op["placa"]))
                    if v:
                        resultado.append(Record({"placa": v["placa"], "janela_inicio": op["janela_inicio"]}))
            return resultado
        return []

    async def fetchval(self, query: str, *args):
        if "SELECT id_veiculo FROM veiculos" in query:
            placa, tenant_id = args[0], args[1]
            v = self.veiculos.get((tenant_id, placa))
            return v["id_veiculo"] if v else None
        return None

    async def execute(self, query: str, *args):
        if self.falhar_na_gravacao:
            raise RuntimeError("Falha forcada no banco para teste de rollback")

        if "INSERT INTO veiculos" in query:
            id_veiculo, placa, modelo, tenant_id = args[0], args[1], args[2], args[3]
            if (tenant_id, placa) not in self.veiculos:
                self.veiculos[(tenant_id, placa)] = {
                    "id_veiculo": id_veiculo,
                    "placa": placa,
                    "modelo": modelo,
                    "tenant_id": tenant_id
                }
        elif "INSERT INTO operacoes" in query:
            id_op, id_veic, orig, orig_lat, orig_lon, dest, dest_lat, dest_lon, dt_inicio, dt_fim, tenant_id, custos = args
            placa = ""
            for (t, p), v in self.veiculos.items():
                if v["id_veiculo"] == id_veic:
                    placa = p
                    break
            self.operacoes[id_op] = {
                "id_operacao": id_op,
                "id_veiculo": id_veic,
                "placa": placa,
                "origem_nome": orig,
                "origem_lat": orig_lat,
                "origem_lon": orig_lon,
                "destino_nome": dest,
                "destino_lat": dest_lat,
                "destino_lon": dest_lon,
                "janela_inicio": dt_inicio,
                "janela_fim": dt_fim,
                "tenant_id": tenant_id,
                "custos_operacionais": custos
            }


class TransacaoCtx:
    def __init__(self, banco: BancoMemoriaManifesto):
        self.banco = banco

    async def __aenter__(self):
        self.banco._backup_estado = (
            dict(self.banco.veiculos),
            dict(self.banco.operacoes)
        )
        self.banco.em_transacao = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.banco.em_transacao = False
        if exc_type is not None:
            if self.banco._backup_estado:
                self.banco.veiculos = dict(self.banco._backup_estado[0])
                self.banco.operacoes = dict(self.banco._backup_estado[1])
            return False
        self.banco.transacoes_feitas += 1
        return False


@pytest.fixture
def conexao_memoria(monkeypatch):
    banco = BancoMemoriaManifesto()

    processar_original = manifesto_service.processar_manifesto

    async def processar_com_relogio_de_teste(*args, **kwargs):
        kwargs.setdefault("referencia_agora", AGORA_TESTE)
        return await processar_original(*args, **kwargs)

    monkeypatch.setattr(manifesto_service, "processar_manifesto", processar_com_relogio_de_teste)

    async def _get_conn():
        yield banco

    app.dependency_overrides[get_connection] = _get_conn
    try:
        yield banco
    finally:
        app.dependency_overrides.pop(get_connection, None)


@pytest.mark.asyncio
async def test_download_manifesto_modelo_csv(conexao_memoria):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/logistica/operacoes/manifesto-modelo")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "manifesto_modelo.csv" in resp.headers["content-disposition"]
        texto = resp.text
        assert "placa,data_saida,hora_saida,origem,destino" in texto
        assert "ABC1D23" in texto
        assert "XYZ-9876" in texto


@pytest.mark.asyncio
async def test_importar_manifesto_dry_run_nao_grava_no_banco(conexao_memoria):
    csv_conteudo = (
        "placa,data_saida,hora_saida,origem,destino,motorista\n"
        "ABC1D23,2026-10-21,12:30,Ribeirao Preto,Campinas,Joao Silva\n"
        "XYZ-9876,2026-10-21,14:15,Araraquara,Sao Paulo,Marcos Lima\n"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "key_admin_demo"}
    ) as client:
        files = {"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")}
        resp = await client.post("/api/v1/logistica/operacoes/importar-manifesto?dry_run=true", files=files)

        assert resp.status_code == 200
        dados = resp.json()
        assert dados["resumo"]["total_linhas"] == 2
        assert dados["resumo"]["validas"] == 2
        assert dados["resumo"]["rejeitadas"] == 0
        assert dados["importadas"] == 0

        assert len(conexao_memoria.veiculos) == 0
        assert len(conexao_memoria.operacoes) == 0


@pytest.mark.asyncio
async def test_importar_manifesto_confirmacao_grava_em_transacao_atomica(conexao_memoria):
    csv_conteudo = (
        "placa,data_saida,hora_saida,origem,destino,motorista\n"
        "ABC1D23,2026-10-21,12:30,Ribeirao Preto,Campinas,Joao Silva\n"
        "XYZ-9876,2026-10-21,14:15,Araraquara,Sao Paulo,Marcos Lima\n"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "key_admin_demo"}
    ) as client:
        files = {"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")}
        resp = await client.post("/api/v1/logistica/operacoes/importar-manifesto?dry_run=false", files=files)

        assert resp.status_code == 200
        dados = resp.json()
        assert dados["resumo"]["total_linhas"] == 2
        assert dados["resumo"]["validas"] == 2
        assert dados["importadas"] == 2

        assert len(conexao_memoria.veiculos) == 2
        assert len(conexao_memoria.operacoes) == 2
        assert conexao_memoria.transacoes_feitas == 1

        chaves_veiculos = list(conexao_memoria.veiculos.keys())
        assert ("demo_corp", "ABC1D23") in chaves_veiculos
        assert ("demo_corp", "XYZ9876") in chaves_veiculos


@pytest.mark.asyncio
async def test_importar_manifesto_idempotencia_reenvio(conexao_memoria):
    csv_conteudo = (
        "placa,data_saida,hora_saida,origem,destino,motorista\n"
        "ABC1D23,2026-10-21,12:30,Ribeirao Preto,Campinas,Joao Silva\n"
        "XYZ-9876,2026-10-21,14:15,Araraquara,Sao Paulo,Marcos Lima\n"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "key_admin_demo"}
    ) as client:
        files1 = {"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")}
        resp1 = await client.post("/api/v1/logistica/operacoes/importar-manifesto?dry_run=false", files=files1)
        assert resp1.status_code == 200
        assert resp1.json()["importadas"] == 2

        files2 = {"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")}
        resp2 = await client.post("/api/v1/logistica/operacoes/importar-manifesto?dry_run=false", files=files2)
        assert resp2.status_code == 200
        dados2 = resp2.json()
        assert dados2["resumo"]["ja_cadastradas"] == 2
        assert dados2["importadas"] == 0

        assert len(conexao_memoria.operacoes) == 2


@pytest.mark.asyncio
async def test_importar_manifesto_arquivo_sujo_do_enunciado(conexao_memoria):
    csv_sujo = (
        "Placa;Data de Saida;Hora Saida;Origem;Destino;Motorista;\n"
        "abc-1d23 ;21/10/2026;2:30;ribeirao preto;CAMPINAS;joao silva;\n"
        "XYZ9876;21/10/26;03:15:00;Araraquara;Sao Paulo;;\n"
        ";;;;;;\n"
        "ABC1D23;21/10/2026;02:30;Ribeirao Preto;Campinas;Joao Silva;\n"
        "=CMD|' /C calc'!A0;21/10/2026;04:00;Sertaozinho;Santos;Pedro;\n"
        "AAA0000;31/02/2026;25:99;Franca;Santos;Ana;\n"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "key_admin_demo"}
    ) as client:
        files = {"file": ("manifesto_sujo.csv", csv_sujo.encode("cp1252"), "text/csv")}
        resp = await client.post("/api/v1/logistica/operacoes/importar-manifesto?dry_run=false", files=files)

        assert resp.status_code == 200
        dados = resp.json()
        assert dados["resumo"]["total_linhas"] == 5
        assert dados["resumo"]["validas"] == 2
        assert dados["resumo"]["rejeitadas"] == 3
        assert dados["resumo"]["duplicadas"] == 1
        assert dados["importadas"] == 2

        linhas_erros = {e["linha"] for e in dados["erros"]}
        assert 5 in linhas_erros
        assert 6 in linhas_erros
        assert 7 in linhas_erros

        assert len(conexao_memoria.operacoes) == 2


@pytest.mark.asyncio
async def test_importar_manifesto_isolamento_multi_tenant(conexao_memoria):
    csv_conteudo = (
        "placa,data_saida,hora_saida,origem,destino\n"
        "ABC1D23,2026-10-21,12:00,Araraquara,Campinas\n"
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp_a = await client.post(
            "/api/v1/logistica/operacoes/importar-manifesto?dry_run=false",
            files={"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")},
            headers={"X-API-Key": "key_admin_demo"}
        )
        assert resp_a.status_code == 200
        assert resp_a.json()["importadas"] == 1

        resp_b = await client.post(
            "/api/v1/logistica/operacoes/importar-manifesto?dry_run=false",
            files={"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")},
            headers={"X-API-Key": "key_admin_express"}
        )
        assert resp_b.status_code == 200
        assert resp_b.json()["importadas"] == 1

        assert ("demo_corp", "ABC1D23") in conexao_memoria.veiculos
        assert ("log_express", "ABC1D23") in conexao_memoria.veiculos

        resp_mismatch = await client.post(
            "/api/v1/logistica/operacoes/importar-manifesto?tenant_id=outro_tenant",
            files={"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")},
            headers={"X-API-Key": "key_admin_demo"}
        )
        assert resp_mismatch.status_code == 403


@pytest.mark.asyncio
async def test_importar_manifesto_rbac_somente_admin_e_operator(conexao_memoria):
    csv_conteudo = "placa,data_saida,hora_saida,origem,destino\nABC1D23,2026-10-21,12:00,Araraquara,Campinas\n"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp_viewer = await client.post(
            "/api/v1/logistica/operacoes/importar-manifesto?dry_run=true",
            files={"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")},
            headers={"X-API-Key": "key_viewer_demo"}
        )
        assert resp_viewer.status_code == 403

        resp_op = await client.post(
            "/api/v1/logistica/operacoes/importar-manifesto?dry_run=true",
            files={"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")},
            headers={"X-API-Key": "key_operator_demo"}
        )
        assert resp_op.status_code == 200


@pytest.mark.asyncio
async def test_importar_manifesto_falha_de_banco_faz_rollback_total(conexao_memoria):
    csv_conteudo = "placa,data_saida,hora_saida,origem,destino\nABC1D23,2026-10-21,12:00,Araraquara,Campinas\n"
    conexao_memoria.falhar_na_gravacao = True

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "key_admin_demo"}
    ) as client:
        files = {"file": ("manifesto.csv", csv_conteudo.encode("utf-8"), "text/csv")}
        resp = await client.post("/api/v1/logistica/operacoes/importar-manifesto?dry_run=false", files=files)

        assert resp.status_code == 500
        assert "Erro ao processar gravacao" in resp.json()["detail"]
        assert len(conexao_memoria.operacoes) == 0


@pytest.mark.asyncio
async def test_importar_manifesto_extensao_invalida(conexao_memoria):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "key_admin_demo"}
    ) as client:
        files = {"file": ("manifesto.xlsx", b"fake binary", "application/octet-stream")}
        resp = await client.post("/api/v1/logistica/operacoes/importar-manifesto", files=files)
        assert resp.status_code == 200
        dados = resp.json()
        assert dados["resumo"]["validas"] == 0
        assert any("Extensao de arquivo invalida" in e["mensagem"] for e in dados["erros"])


@pytest.mark.asyncio
async def test_frontend_manifesto_estatico_e_elementos_ui():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp_html = await client.get("/static/b2b.html")
        assert resp_html.status_code == 200
        html = resp_html.text

        assert "window.PainelManifesto.abrir()" in html
        assert "Importar Viagens (CSV)" in html

        assert 'id="modal-manifesto"' in html
        assert 'id="drop-zone-manifesto"' in html
        assert 'id="manifesto-file-input"' in html
        assert 'id="manifesto-estado-inicial"' in html
        assert 'id="manifesto-estado-carregando"' in html
        assert 'id="manifesto-estado-erro"' in html
        assert 'id="manifesto-estado-previa"' in html
        assert 'id="manifesto-estado-sucesso"' in html

        assert 'id="prev-total"' in html
        assert 'id="prev-validas"' in html
        assert 'id="prev-rejeitadas"' in html
        assert 'id="btn-confirmar-manifesto"' in html
        assert 'id="btn-baixar-rejeitadas"' in html
        assert 'id="tabela-erros-manifesto"' in html
        assert "window.PainelManifesto.baixarModelo()" in html
        assert 'id="btn-demo-araraquara"' in html
        assert "Carregar Viagens de Exemplo (Araraquara)" in html

        import re
        from urllib.parse import urlsplit
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        recurso = next((url for url in scripts if urlsplit(url).path == "/static/painel-manifesto.js"), None)
        assert recurso is not None
        resp_js = await client.get(recurso)
        assert resp_js.status_code == 200
        assert "window.PainelManifesto" in resp_js.text
        assert "baixarLinhasRejeitadas" in resp_js.text
        assert "atualizarVisibilidadeDemo" in resp_js.text

