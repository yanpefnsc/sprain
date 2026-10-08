import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional

WEBHOOKS_CONFIG: Dict[str, Dict[str, Any]] = {
    "demo_corp": {
        "url": "https://tms.democorp.com/webhooks/sprain",
        "secret": "secret_demo_sprain_2026",
        "eventos": ["ALERTA_ALAGAMENTO", "ROTA_RECALCULADA", "SLA_RISCO"]
    }
}

class WebhookDispatcher:
    @classmethod
    def configurar_webhook(cls, tenant_id: str, url: str, secret: str, eventos: list) -> Dict[str, Any]:
        WEBHOOKS_CONFIG[tenant_id] = {
            "url": url,
            "secret": secret,
            "eventos": eventos
        }
        return {"tenant_id": tenant_id, "status": "CONFIGURADO", "url": url, "eventos": eventos}

    @classmethod
    def gerar_assinatura(cls, secret: str, payload_bytes: bytes) -> str:
        return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def disparar_evento_sincrono(cls, tenant_id: str, evento: str, dados: dict) -> Dict[str, Any]:
        config = WEBHOOKS_CONFIG.get(tenant_id)
        if not config:
            return {"sucesso": False, "motivo": "WEBHOOK_NAO_CONFIGURADO"}

        payload = {
            "evento": evento,
            "timestamp": time.time(),
            "tenant_id": tenant_id,
            "payload": dados
        }
        payload_json = json.dumps(payload, sort_keys=True)
        assinatura = cls.gerar_assinatura(config["secret"], payload_json.encode("utf-8"))

        headers_envio = {
            "Content-Type": "application/json",
            "X-SPRain-Signature": assinatura,
            "X-SPRain-Event": evento
        }

        return {
            "sucesso": True,
            "url_destino": config["url"],
            "headers": headers_envio,
            "payload_enviado": payload,
            "assinatura_valida": True
        }
