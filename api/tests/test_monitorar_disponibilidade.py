"""A sonda deve preservar alertas entre execuções separadas do timer."""

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import monitorar_disponibilidade as monitor


def opcoes(tmp_path):
    return argparse.Namespace(
        url="https://piloto.exemplo.com/api/v1/health/readiness",
        webhook_url="https://discord.com/api/webhooks/exemplo",
        state_file=tmp_path / "estado.json", failure_threshold=2,
        timeout=8.0, allow_http_local_test=False,
    )


def test_queda_e_recuperacao_geram_um_aviso_cada(tmp_path, monkeypatch):
    respostas = iter([(False, "HTTP 503")] * 3 + [(True, "READY")] * 2)
    avisos = []
    monkeypatch.setattr(monitor, "probe", lambda *_: next(respostas))
    monkeypatch.setattr(monitor, "notify", lambda _, mensagem, __: avisos.append(mensagem))
    args = opcoes(tmp_path)

    assert [monitor.check(args) for _ in range(5)] == [1, 1, 1, 0, 0]
    assert len(avisos) == 2
    assert "INDISPONÍVEL" in avisos[0]
    assert "RECUPERADO" in avisos[1]
    assert json.loads(args.state_file.read_text(encoding="utf-8"))["alerted"] is False


def test_falha_no_webhook_mantem_alerta_pendente(tmp_path, monkeypatch):
    avisos = []

    def enviar(_, mensagem, __):
        avisos.append(mensagem)
        if len(avisos) == 1:
            raise RuntimeError("destino indisponível")

    monkeypatch.setattr(monitor, "probe", lambda *_: (False, "HTTP 503"))
    monkeypatch.setattr(monitor, "notify", enviar)
    args = opcoes(tmp_path)

    assert monitor.check(args) == 1
    with pytest.raises(RuntimeError, match="destino indisponível"):
        monitor.check(args)
    assert json.loads(args.state_file.read_text(encoding="utf-8"))["alerted"] is False

    assert monitor.check(args) == 1
    assert len(avisos) == 2
    assert json.loads(args.state_file.read_text(encoding="utf-8"))["alerted"] is True
