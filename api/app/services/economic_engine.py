from typing import Dict, Any, List

class EconomicDecisionEngine:
    @staticmethod
    def evaluate_route_tradeoff(
        distancia_km: float,
        tempo_min: float,
        probabilidade_atraso: float,
        probabilidade_bloqueio: float,
        consumo_km_l: float,
        preco_diesel_litro: float,
        custo_hora_veiculo: float,
        custo_hora_motorista: float,
        valor_frete: float,
        valor_carga: float,
        multa_por_hora_atraso: float,
        janela_limite_min: float
    ) -> Dict[str, Any]:
        consumo_litros = distancia_km / max(0.1, consumo_km_l)
        custo_combustivel = round(consumo_litros * preco_diesel_litro, 2)
        
        horas_operacao = tempo_min / 60.0
        custo_tempo_operacional = round(horas_operacao * (custo_hora_veiculo + custo_hora_motorista), 2)
        
        minutos_atraso_esperado = max(0.0, (tempo_min - janela_limite_min)) * probabilidade_atraso
        custo_multa_atraso = round((minutos_atraso_esperado / 60.0) * multa_por_hora_atraso, 2)
        
        risco_bloqueio_carga = round(probabilidade_bloqueio * (valor_carga * 0.05 + 500.0), 2)
        
        custo_total = round(custo_combustivel + custo_tempo_operacional + custo_multa_atraso + risco_bloqueio_carga, 2)
        resultado_liquido = round(valor_frete - custo_total, 2)
        
        return {
            "distancia_km": round(distancia_km, 2),
            "tempo_estimado_min": round(tempo_min, 1),
            "custo_combustivel_brl": custo_combustivel,
            "custo_tempo_operacional_brl": custo_tempo_operacional,
            "custo_multa_atraso_brl": custo_multa_atraso,
            "risco_perda_alagamento_brl": risco_bloqueio_carga,
            "custo_total_estimado_brl": custo_total,
            "resultado_liquido_brl": resultado_liquido
        }

    @classmethod
    def compare_and_recommend(
        cls,
        rota_direta: Dict[str, Any],
        rota_segura: Dict[str, Any],
        parametros: Dict[str, Any]
    ) -> Dict[str, Any]:
        direta_eval = cls.evaluate_route_tradeoff(
            distancia_km=rota_direta["distancia_km"],
            tempo_min=rota_direta["tempo_min"],
            probabilidade_atraso=rota_direta.get("probabilidade_atraso", 0.65),
            probabilidade_bloqueio=rota_direta.get("probabilidade_bloqueio", 0.40),
            consumo_km_l=parametros.get("consumo_km_l", 3.0),
            preco_diesel_litro=parametros.get("preco_diesel_litro", 6.20),
            custo_hora_veiculo=parametros.get("custo_hora_veiculo", 50.0),
            custo_hora_motorista=parametros.get("custo_hora_motorista", 35.0),
            valor_frete=parametros.get("valor_frete", 600.0),
            valor_carga=parametros.get("valor_carga", 25000.0),
            multa_por_hora_atraso=parametros.get("multa_por_hora_atraso", 150.0),
            janela_limite_min=parametros.get("janela_limite_min", 45.0)
        )
        
        segura_eval = cls.evaluate_route_tradeoff(
            distancia_km=rota_segura["distancia_km"],
            tempo_min=rota_segura["tempo_min"],
            probabilidade_atraso=rota_segura.get("probabilidade_atraso", 0.10),
            probabilidade_bloqueio=rota_segura.get("probabilidade_bloqueio", 0.02),
            consumo_km_l=parametros.get("consumo_km_l", 3.0),
            preco_diesel_litro=parametros.get("preco_diesel_litro", 6.20),
            custo_hora_veiculo=parametros.get("custo_hora_veiculo", 50.0),
            custo_hora_motorista=parametros.get("custo_hora_motorista", 35.0),
            valor_frete=parametros.get("valor_frete", 600.0),
            valor_carga=parametros.get("valor_carga", 25000.0),
            multa_por_hora_atraso=parametros.get("multa_por_hora_atraso", 150.0),
            janela_limite_min=parametros.get("janela_limite_min", 45.0)
        )
        
        escolha_segura = segura_eval["resultado_liquido_brl"] >= direta_eval["resultado_liquido_brl"]
        delta_lucro = round(abs(segura_eval["resultado_liquido_brl"] - direta_eval["resultado_liquido_brl"]), 2)
        
        return {
            "recomendacao": "ROTA_ALTERNATIVA_SEGURA" if escolha_segura else "ROTA_DIRETA_ORIGINAL",
            "justificativa_financeira": (
                f"A rota alternativa gera vantagem economica de R$ {delta_lucro} protegendo a margem contra risco de atraso contratual e sinistro por alagamento."
                if escolha_segura else
                f"A rota direta se mantem economicamente superior em R$ {delta_lucro}, pois o custo adicional do desvio excede a mitigacao do risco."
            ),
            "tradeoff": {
                "rota_direta": direta_eval,
                "rota_alternativa": segura_eval,
                "vantagem_economica_brl": delta_lucro
            }
        }