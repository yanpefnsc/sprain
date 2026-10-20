import math
import time
from typing import Any, Dict, Optional

try:
    from app.services.limiares_chuva import LIMIARES, LIMIARES_VENTO
except ImportError:
    from services.limiares_chuva import LIMIARES, LIMIARES_VENTO

TETO_CHUVA_MM = 1000.0
TETO_VENTO_KMH = 300.0

CLASSIFICACAO = {
    "VERMELHO_EXTRAORDINARIO": ("CRITICO", "SUSPENDER_OPERACOES_OU_DESVIAR_TOTAL"),
    "LARANJA_SEVERO": ("ALTO", "ROTEAMENTO_PREVENTIVO_OBRIGATORIO"),
    "AMARELO_ATENCAO": ("MODERADO", "MONITORAMENTO_ATIVO_TELEMETRIA"),
    "VERDE_ESTAVEL": ("BAIXO", "FLUXO_NORMAL"),
    "INDISPONIVEL": ("DESCONHECIDO", "DADO_METEOROLOGICO_INDISPONIVEL"),
}


def _medida_valida(valor: Any, teto: float) -> Optional[float]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numero) or numero < 0.0 or numero > teto:
        return None
    return numero


class SevereWeatherEngine:
    @staticmethod
    def parse_alert_severity(precipitacao_mm: Any = None, rajada_vento_kmh: Any = None) -> Dict[str, Any]:
        chuva = _medida_valida(precipitacao_mm, TETO_CHUVA_MM)
        vento = _medida_valida(rajada_vento_kmh, TETO_VENTO_KMH)
        c = chuva or 0.0
        v = vento or 0.0

        if c >= LIMIARES["critico"] or v >= LIMIARES_VENTO["critico"]:
            nivel = "VERMELHO_EXTRAORDINARIO"
        elif c >= LIMIARES["severo"] or v >= LIMIARES_VENTO["severo"]:
            nivel = "LARANJA_SEVERO"
        elif c >= LIMIARES["atencao"]:
            nivel = "AMARELO_ATENCAO"
        elif chuva is None:
            nivel = "INDISPONIVEL"
        else:
            nivel = "VERDE_ESTAVEL"

        risco, recomendacao = CLASSIFICACAO[nivel]
        return {
            "nivel_alerta": nivel,
            "classificacao_risco": risco,
            "recomendacao_operacional": recomendacao,
            "dados_parciais": chuva is None or vento is None,
            "telemetria": {
                "precipitacao_mm": None if chuva is None else round(chuva, 1),
                "rajada_vento_kmh": None if vento is None else round(vento, 1),
                "timestamp_avaliacao": time.time(),
            },
        }
