from abc import ABC, abstractmethod
import urllib.request
import json
import re

class WeatherProvider(ABC):
    @abstractmethod
    def get_current_rainfall(self, station_id: str) -> float:
        pass

    @abstractmethod
    def get_forecast_rainfall(self, lat: float, lon: float, days: int = 1) -> float:
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

    def get_forecast_rainfall(self, lat: float, lon: float, days: int = 1) -> float:
        return 0.0

class SimulatedWeatherProvider(WeatherProvider):
    def __init__(self, fixed_mm: float = 0.0):
        self.fixed_mm = fixed_mm

    def get_current_rainfall(self, station_id: str) -> float:
        return self.fixed_mm

    def get_forecast_rainfall(self, lat: float, lon: float, days: int = 1) -> float:
        return self.fixed_mm

class OpenMeteoProvider(WeatherProvider):
    def get_current_rainfall(self, station_id: str) -> float:
        return 0.0

    def get_forecast_rainfall(self, lat: float, lon: float, days: int = 1) -> float:
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=precipitation_sum&timezone=America%2FSao_Paulo&forecast_days={days+1}"
            req = urllib.request.Request(url, headers={"User-Agent": "SPRain-B2B/3.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "daily" in data and "precipitation_sum" in data["daily"]:
                    return float(data["daily"]["precipitation_sum"][days])
            return 0.0
        except Exception:
            return 0.0
