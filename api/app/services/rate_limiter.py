import time
from typing import Dict, List, Tuple
from fastapi import HTTPException, Request, Header

PLAN_LIMITS: Dict[str, int] = {
    "demo_corp": 60,
    "log_express": 120,
    "test_limited": 3
}

class TenantRateLimiter:
    _history: Dict[str, List[float]] = {}
    _window_seconds: float = 60.0

    @classmethod
    def check_rate_limit(cls, tenant_id: str) -> Tuple[int, int]:
        agora = time.time()
        limite = PLAN_LIMITS.get(tenant_id, 30)
        
        if tenant_id not in cls._history:
            cls._history[tenant_id] = []
            
        timestamps = [t for t in cls._history[tenant_id] if agora - t < cls._window_seconds]
        cls._history[tenant_id] = timestamps

        if len(timestamps) >= limite:
            retry_after = int(cls._window_seconds - (agora - timestamps[0])) + 1
            raise HTTPException(
                status_code=429,
                detail="Limite de requisicoes por minuto excedido para o seu plano corporativo.",
                headers={
                    "Retry-After": str(max(1, retry_after)),
                    "X-RateLimit-Limit": str(limite),
                    "X-RateLimit-Remaining": "0"
                }
            )

        cls._history[tenant_id].append(agora)
        restantes = limite - len(cls._history[tenant_id])
        return limite, restantes

    @classmethod
    def reset(cls):
        cls._history.clear()
