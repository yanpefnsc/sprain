from typing import Dict, Any
import time

class SevereWeatherEngine:
    @staticmethod
    def parse_alert_severity(precipitacao_mm: float, rajada_vento_kmh: float = 30.0) -> Dict[str, Any]:
        if precipitacao_mm >= 80.0 or rajada_vento_kmh >= 75.0:
            nivel = "VERMELHO_EXTRAORDINARIO"
            risco = "CRITICO"
            recomendacao = "SUSPENDER_OPERACOES_OU_DESVIAR_TOTAL"
        elif precipitacao_mm >= 50.0 or rajada_vento_kmh >= 55.0:
            nivel = "LARANJA_SEVERO"
            risco = "ALTO"
            recomendacao = "ROTEAMENTO_PREVENTIVO_OBRIGATORIO"
        elif precipitacao_mm >= 25.0:
            nivel = "AMARELO_ATENCAO"
            risco = "MODERADO"
            recomendacao = "MONITORAMENTO_ATIVO_TELEMETRIA"
        else:
            nivel = "VERDE_ESTAVEL"
            risco = "BAIXO"
            recomendacao = "FLUXO_NORMAL"
            
        return {
            "nivel_alerta": nivel,
            "classificacao_risco": risco,
            "recomendacao_operacional": recomendacao,
            "telemetria": {
                "precipitacao_mm": round(precipitacao_mm, 1),
                "rajada_vento_kmh": round(rajada_vento_kmh, 1),
                "timestamp_avaliacao": time.time()
            }
        }
