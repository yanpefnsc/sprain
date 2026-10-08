from abc import ABC, abstractmethod
import urllib.request
import re

class WeatherProvider(ABC):
    @abstractmethod
    def get_current_rainfall(self, station_id: str) -> float:
        pass

    @abstractmethod
    def get_forecast_rainfall(self, station_id: str, hours: int = 24) -> float:
        pass

class CGEWeatherProvider(WeatherProvider):
    URL_BASE = "https://www.cgesp.org/v3/estacao.jsp?POSTO="

    def get_current_rainfall(self, station_id: str = "1000864") -> float:
        try:
            url = f"{self.URL_BASE}{station_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "SPRain-B2B/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            texto = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))
            m_atual = re.search(r'Per[íi\.]*\s*Atual[:\s]+([\d\.,]+)\s*mm', texto, re.I)
            m_ant = re.search(r'Per[íi\.]*\s*Anterior[:\s]+([\d\.,]+)\s*mm', texto, re.I)
            v1 = float(m_atual.group(1).replace(",", ".")) if m_atual else 0.0
            v2 = float(m_ant.group(1).replace(",", ".")) if m_ant else 0.0
            return round(v1 + v2, 1)
        except Exception:
            return 0.0

    def get_forecast_rainfall(self, station_id: str = "1000864", hours: int = 24) -> float:
        return 0.0

class SimulatedWeatherProvider(WeatherProvider):
    def __init__(self, fixed_mm: float = 0.0):
        self.fixed_mm = fixed_mm

    def get_current_rainfall(self, station_id: str) -> float:
        return self.fixed_mm

    def get_forecast_rainfall(self, station_id: str, hours: int = 24) -> float:
        return self.fixed_mm
