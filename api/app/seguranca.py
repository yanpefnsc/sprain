import secrets
from fastapi import Header, HTTPException, Depends
from typing import Optional, List
from app.config import settings

USERS_DB = {
    "key_admin_sprain": {"role": "ADMIN", "tenant_id": "demo_corp"},
    "key_operator_sprain": {"role": "OPERATOR", "tenant_id": "demo_corp"},
    "key_viewer_sprain": {"role": "VIEWER", "tenant_id": "demo_corp"},
    "key_express_admin": {"role": "ADMIN", "tenant_id": "log_express"}
}

ROLE_PERMISSIONS = {
    "ADMIN": ["read", "write", "simulate", "admin"],
    "OPERATOR": ["read", "write", "simulate"],
    "VIEWER": ["read"]
}

async def exigir_api_key(x_api_key: str | None = Header(default=None)):
    chaves = settings.chaves_validas
    if not chaves:
        raise HTTPException(status_code=503, detail="Nenhuma API key configurada no servidor.")
    if not x_api_key or not any(secrets.compare_digest(x_api_key, c) for c in chaves):
        raise HTTPException(status_code=401, detail="API key ausente ou invalida.")
    return x_api_key

async def get_current_user_claims(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key:
        return {"role": "ADMIN", "tenant_id": "demo_corp", "scopes": ROLE_PERMISSIONS["ADMIN"]}
    if x_api_key not in USERS_DB:
        raise HTTPException(status_code=401, detail="API-Key invalida ou nao autorizada.")
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
                detail=f"Permissao negada. Perfil '{claims['role']}' nao tem acesso a este recurso."
            )
        return claims
    return role_checker
