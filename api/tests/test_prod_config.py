import pytest
from fastapi import HTTPException
from app import seguranca
from app.config import Settings

def test_producao_recusa_sem_segredos(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DB_PASSWORD", "enchentes")
    with pytest.raises(RuntimeError):
        seguranca.validar_configuracao_producao()

def test_producao_recusa_chave_demo(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DB_PASSWORD", "senha_forte_exclusiva_prod_2026")
    monkeypatch.setenv("WEBHOOK_SECRET_KEY", "chave_fernet_valida_prod_2026_123456")
    monkeypatch.setenv("TENANT_API_KEYS", "key_admin_demo:ADMIN:demo_corp")
    with pytest.raises(RuntimeError):
        seguranca.validar_configuracao_producao()

def test_producao_sem_tenant_keys_bloqueia_fallback_demo(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TENANT_API_KEYS", raising=False)
    with pytest.raises(HTTPException) as exc:
        seguranca.carregar_chaves_tenants()
    assert exc.value.status_code == 503


def test_producao_recusa_api_keys_ausentes(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DB_PASSWORD", "senha_forte_exclusiva_prod_2026")
    monkeypatch.setenv("WEBHOOK_SECRET_KEY", "chave_exclusiva_de_teste")
    monkeypatch.setenv("TENANT_API_KEYS", "chave_teste:ADMIN:empresa_teste")
    monkeypatch.setattr(seguranca.settings, "API_KEYS", "")
    with pytest.raises(RuntimeError, match="API_KEYS"):
        seguranca.validar_configuracao_producao()


def test_cors_producao_restringe_origens(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    configuracao = Settings(_env_file=None, CORS_ORIGINS="https://painel.exemplo.com, https://ops.exemplo.com/")
    assert configuracao.origens_cors == ["https://painel.exemplo.com", "https://ops.exemplo.com"]
    assert Settings(_env_file=None).origens_cors == []


def test_cors_producao_recusa_curinga(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        Settings(_env_file=None, CORS_ORIGINS="https://painel.exemplo.com,*").origens_cors


def test_coleta_automatica_corredor_fica_desligada_em_producao(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "demonstracao_habilitada", lambda: False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert not main.coleta_corredor_automatica_habilitada()

    monkeypatch.setenv("ENVIRONMENT", "testing")
    assert main.coleta_corredor_automatica_habilitada()
    monkeypatch.setattr(main, "demonstracao_habilitada", lambda: True)
    assert not main.coleta_corredor_automatica_habilitada()
