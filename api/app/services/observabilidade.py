import time
from typing import Dict, Any, List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class MetricsCollector:
    _total_requisicoes: int = 0
    _total_erros: int = 0
    _tempo_total_ms: float = 0.0
    _rotas_lentas: List[Dict[str, Any]] = []
    _erros_recentes: List[Dict[str, Any]] = []
    _latencias_por_rota: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def registrar(cls, metodo: str, rota: str, status_code: int, duracao_ms: float):
        cls._total_requisicoes += 1
        cls._tempo_total_ms += duracao_ms

        if status_code >= 400:
            cls._total_erros += 1
            if len(cls._erros_recentes) >= 50:
                cls._erros_recentes.pop(0)
            cls._erros_recentes.append({
                "metodo": metodo,
                "rota": rota,
                "status_code": status_code,
                "duracao_ms": round(duracao_ms, 2),
                "timestamp": time.time()
            })

        if duracao_ms >= 500.0:
            if len(cls._rotas_lentas) >= 50:
                cls._rotas_lentas.pop(0)
            cls._rotas_lentas.append({
                "metodo": metodo,
                "rota": rota,
                "duracao_ms": round(duracao_ms, 2),
                "timestamp": time.time()
            })

        chave_rota = f"{metodo} {rota}"
        if chave_rota not in cls._latencias_por_rota:
            cls._latencias_por_rota[chave_rota] = {
                "chamadas": 0,
                "tempo_total_ms": 0.0,
                "max_ms": duracao_ms,
                "min_ms": duracao_ms
            }
        
        info = cls._latencias_por_rota[chave_rota]
        info["chamadas"] += 1
        info["tempo_total_ms"] += duracao_ms
        if duracao_ms > info["max_ms"]:
            info["max_ms"] = duracao_ms
        if duracao_ms < info["min_ms"]:
            info["min_ms"] = duracao_ms

    @classmethod
    def obter_metricas(cls) -> Dict[str, Any]:
        media_global = round(cls._tempo_total_ms / cls._total_requisicoes, 2) if cls._total_requisicoes > 0 else 0.0
        taxa_erro = round((cls._total_erros / cls._total_requisicoes) * 100.0, 2) if cls._total_requisicoes > 0 else 0.0

        resumo_rotas = {}
        for rota, dados in cls._latencias_por_rota.items():
            resumo_rotas[rota] = {
                "chamadas": dados["chamadas"],
                "latencia_media_ms": round(dados["tempo_total_ms"] / dados["chamadas"], 2),
                "min_ms": round(dados["min_ms"], 2),
                "max_ms": round(dados["max_ms"], 2)
            }

        return {
            "status_monitor": "OPERACIONAL",
            "total_requisicoes": cls._total_requisicoes,
            "total_erros": cls._total_erros,
            "taxa_erro_pct": taxa_erro,
            "latencia_media_global_ms": media_global,
            "rotas_lentas_detectadas": len(cls._rotas_lentas),
            "historico_rotas_lentas": cls._rotas_lentas[-10:],
            "erros_recentes": cls._erros_recentes[-10:],
            "detalhamento_por_rota": resumo_rotas
        }

    @classmethod
    def resetar(cls):
        cls._total_requisicoes = 0
        cls._total_erros = 0
        cls._tempo_total_ms = 0.0
        cls._rotas_lentas.clear()
        cls._erros_recentes.clear()
        cls._latencias_por_rota.clear()

class ObservabilidadeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inicio = time.perf_counter()
        response = await call_next(request)
        duracao_ms = (time.perf_counter() - inicio) * 1000.0
        
        MetricsCollector.registrar(
            metodo=request.method,
            rota=request.url.path,
            status_code=response.status_code,
            duracao_ms=duracao_ms
        )

        response.headers["X-Process-Time-Ms"] = str(round(duracao_ms, 2))
        return response