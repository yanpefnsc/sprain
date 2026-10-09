import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from app import database

ARQUIVO_SCHEMA = Path(__file__).resolve().parents[3] / "db" / "ci" / "02_webhooks_tenant.sql"


def _fernet() -> Fernet:
    chave = os.getenv("WEBHOOK_SECRET_KEY", "").strip()
    if chave:
        return Fernet(chave.encode("utf-8"))
    derivada = hashlib.sha256(b"sprain-dev-webhook-key").digest()
    return Fernet(base64.urlsafe_b64encode(derivada))


class WebhookDispatcher:
    @classmethod
    async def garantir_schema(cls) -> None:
        sql = ARQUIVO_SCHEMA.read_text(encoding="utf-8")
        async with database.db_pool.acquire() as conn:
            await conn.execute(sql)

    @classmethod
    async def configurar_webhook(cls, conn, tenant_id: str, url: str, secret: str, eventos: list) -> Dict[str, Any]:
        secret_cifrado = _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")
        await conn.execute(
            """
            INSERT INTO webhooks_tenant (tenant_id, url, secret_cifrado, eventos)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tenant_id) DO UPDATE
            SET url = EXCLUDED.url,
                secret_cifrado = EXCLUDED.secret_cifrado,
                eventos = EXCLUDED.eventos,
                atualizado_em = now();
            """,
            tenant_id, url, secret_cifrado, eventos,
        )
        return {"tenant_id": tenant_id, "status": "CONFIGURADO", "url": url, "eventos": eventos}

    @classmethod
    def gerar_assinatura(cls, secret: str, payload_bytes: bytes) -> str:
        return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    @classmethod
    async def disparar_evento_sincrono(cls, conn, tenant_id: str, evento: str, dados: dict) -> Dict[str, Any]:
        row = await conn.fetchrow(
            "SELECT url, secret_cifrado FROM webhooks_tenant WHERE tenant_id = $1;",
            tenant_id,
        )
        if row is None:
            return {"sucesso": False, "motivo": "WEBHOOK_NAO_CONFIGURADO"}

        try:
            secret = _fernet().decrypt(row["secret_cifrado"].encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return {"sucesso": False, "motivo": "SEGREDO_ILEGIVEL"}

        payload = {
            "evento": evento,
            "timestamp": time.time(),
            "tenant_id": tenant_id,
            "payload": dados
        }
        payload_json = json.dumps(payload, sort_keys=True)
        assinatura = cls.gerar_assinatura(secret, payload_json.encode("utf-8"))

        headers_envio = {
            "Content-Type": "application/json",
            "X-SPRain-Signature": assinatura,
            "X-SPRain-Event": evento
        }

        return {
            "sucesso": True,
            "url_destino": row["url"],
            "headers": headers_envio,
            "payload_enviado": payload,
            "assinatura_valida": True
        }
