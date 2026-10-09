import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.services import webhook_dispatcher
from app.services.webhook_dispatcher import WebhookDispatcher


class Registro:
    def __init__(self):
        self.chamadas = []


def subir_servidor(codigo, destino=None):
    registro = Registro()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = self.rfile.read(tamanho)
            registro.chamadas.append({
                "corpo": corpo,
                "caminho": self.path,
                "assinatura": self.headers.get("X-SPRain-Signature"),
            })
            self.send_response(codigo)
            if destino:
                self.send_header("Location", destino)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, registro


def derrubar(servidor):
    servidor.shutdown()
    servidor.server_close()


def test_envio_entrega_corpo_assinado(monkeypatch):
    monkeypatch.setattr(webhook_dispatcher, "is_safe_url", lambda url: True)
    servidor, registro = subir_servidor(200)
    try:
        url = f"http://127.0.0.1:{servidor.server_port}/hook"
        corpo = json.dumps({"evento": "ALERTA_ALAGAMENTO"}, sort_keys=True).encode("utf-8")
        assinatura = WebhookDispatcher.gerar_assinatura("segredo_de_teste", corpo)
        headers = {"Content-Type": "application/json", "X-SPRain-Signature": assinatura}
        resultado = WebhookDispatcher._enviar_http(url, headers, corpo)
    finally:
        derrubar(servidor)
    assert resultado == {"enviado": True, "codigo_http": 200, "entregue": True}
    assert len(registro.chamadas) == 1
    assert registro.chamadas[0]["corpo"] == corpo
    assert registro.chamadas[0]["assinatura"] == assinatura


def test_envio_nao_segue_redirect(monkeypatch):
    monkeypatch.setattr(webhook_dispatcher, "is_safe_url", lambda url: True)
    servidor, registro = subir_servidor(302, destino="/outro")
    try:
        url = f"http://127.0.0.1:{servidor.server_port}/hook"
        resultado = WebhookDispatcher._enviar_http(url, {}, b"{}")
    finally:
        derrubar(servidor)
    assert resultado == {"enviado": True, "codigo_http": 302, "entregue": False}
    assert len(registro.chamadas) == 1
    assert registro.chamadas[0]["caminho"] == "/hook"


def test_envio_recusa_url_interna():
    servidor, registro = subir_servidor(200)
    try:
        url = f"http://127.0.0.1:{servidor.server_port}/hook"
        resultado = WebhookDispatcher._enviar_http(url, {}, b"{}")
    finally:
        derrubar(servidor)
    assert resultado == {"enviado": False, "motivo": "URL_BLOQUEADA"}
    assert registro.chamadas == []


def test_envio_falha_de_conexao(monkeypatch):
    monkeypatch.setattr(webhook_dispatcher, "is_safe_url", lambda url: True)
    servidor, _ = subir_servidor(200)
    porta = servidor.server_port
    derrubar(servidor)
    resultado = WebhookDispatcher._enviar_http(f"http://127.0.0.1:{porta}/hook", {}, b"{}")
    assert resultado["enviado"] is False
    assert resultado["motivo"] == "FALHA_ENVIO"


@pytest.mark.asyncio
async def test_enviar_resultado_manda_o_payload_assinado(monkeypatch):
    monkeypatch.setattr(webhook_dispatcher, "is_safe_url", lambda url: True)
    servidor, registro = subir_servidor(202)
    try:
        payload = {"evento": "ROTA_RECALCULADA", "tenant_id": "demo_corp", "payload": {"id_trecho": 7}}
        corpo = json.dumps(payload, sort_keys=True).encode("utf-8")
        assinatura = WebhookDispatcher.gerar_assinatura("segredo_de_teste", corpo)
        resultado = {
            "url_destino": f"http://127.0.0.1:{servidor.server_port}/hook",
            "headers": {"Content-Type": "application/json", "X-SPRain-Signature": assinatura},
            "payload_enviado": payload,
        }
        envio = await WebhookDispatcher.enviar_resultado(resultado)
    finally:
        derrubar(servidor)
    assert envio == {"enviado": True, "codigo_http": 202, "entregue": True}
    assert registro.chamadas[0]["corpo"] == corpo
    assert registro.chamadas[0]["assinatura"] == assinatura
