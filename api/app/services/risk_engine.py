from typing import Dict, Any

class RiskEngine:
    @staticmethod
    def calculate_segment_risk(ivi_score: float, rain_mm: float) -> Dict[str, Any]:
        ivi = float(ivi_score or 0.0)
        chuva_fator = min(1.0, rain_mm / 100.0)
        dynamic_score = min(100.0, ivi * (0.6 + 0.6 * chuva_fator))
        
        if dynamic_score >= 80.0:
            level = "CRITICO"
            status = "BLOQUEADO"
            weight_multiplier = 1000.0
        elif dynamic_score >= 60.0:
            level = "RISCO"
            status = "RISCO"
            weight_multiplier = 25.0
        elif dynamic_score >= 40.0:
            level = "ATENCAO"
            status = "ATENCAO"
            weight_multiplier = 5.0
        else:
            level = "NORMAL"
            status = "NORMAL"
            weight_multiplier = 1.0

        return {
            "score": round(dynamic_score, 2),
            "level": level,
            "status": status,
            "multiplier": weight_multiplier
        }
