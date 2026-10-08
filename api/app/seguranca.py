import os
import secrets
from fastapi import Header, HTTPException, Depends
from typing import Optional, List
from app.config import settings

def carregar_chaves_tenants() -> dict:
    env_keys = os.getenv("TENANT_API_KEYS", "")
    if env_keys:
        banco = {}
        for entrada in env_keys.split(";"):
            partes = entrada.strip().split(":")
            if len(partes) == 3:
                k, role, tenant = partes
                banco[k.strip()] = {"role": role.strip().upper(), "tenant_id": tenant.strip()}
        if banco:
            return banco
    return {
        "key_admin_demo": {"role": "ADMIN", "tenant_id": "demo_corp"},
        "key_operator_demo": {"role": "OPERATOR", "tenant_id": "demo_corp"},
        "key_viewer_demo": {"role": "VIEWER", "tenant_id": "demo_corp"},
        "key_admin_express": {"role": "ADMIN", "tenant_id": "log_express"}
    }

USERS_DB = carregar_chaves_tenants()

ROLE_PERMISSIONS = {
    "ADMIN": ["read", "write", "simulate", "admin"],
    "OPERATOR": ["read", "write", "simulate"],
    "VIEWER": ["read"]
}

async def exigir_api_key(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Autenticacao necessaria. Header X-API-Key ausente.")
    chaves = settings.chaves_validas
    if chaves and not any(secrets.compare_digest(x_api_key, c) for c in chaves):
        raise HTTPException(status_code=401, detail="API key invalida.")
    return x_api_key

async def get_current_user_claims(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Nao autorizado. Forneca o cabecalho X-API-Key.")
    if x_api_key not in USERS_DB:
        raise HTTPException(status_code=401, detail="API-Key nao reconhecida ou sem permissao.")
    user = USERS_DB[x_api_key]
    user_scopes = ROLE_PERMISSIONS.get(user["role"], ["read"])
    return {
        "role": user["role"],
        "tenant_id": user["tenant_id"],
        "scopes": user_scopes
    }

def require_role(allowed_roles: List[str]):
    async def role_checker(claims: dict = Depends(get_current_user_claims)):
        if claims["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permissao negada. Perfil '{claims['role']}' nao autorizado."
            )
        return claims
    return role_checker

def resolver_tenant_autenticado(claims: dict = Depends(get_current_user_claims)) -> str:
    return claims["tenant_id"]