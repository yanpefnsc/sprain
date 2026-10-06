import secrets
from fastapi import Header, HTTPException
from app.config import settings


async def exigir_api_key(x_api_key: str | None = Header(default=None)):
    chaves = settings.chaves_validas
    if not chaves:
        raise HTTPException(status_code=503, detail="Nenhuma API key configurada no servidor.")
    if not x_api_key or not any(secrets.compare_digest(x_api_key, c) for c in chaves):
        raise HTTPException(status_code=401, detail="API key ausente ou invalida.")