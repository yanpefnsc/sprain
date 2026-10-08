from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ParametrosDecisaoEconomica(BaseModel):
    consumo_km_l: float = Field(default=3.0, ge=0.5, le=20.0)
    preco_diesel_litro: float = Field(default=6.20, ge=1.0)
    custo_hora_veiculo: float = Field(default=50.0, ge=0.0)
    custo_hora_motorista: float = Field(default=35.0, ge=0.0)
    valor_frete: float = Field(default=600.0, ge=0.0)
    valor_carga: float = Field(default=25000.0, ge=0.0)
    multa_por_hora_atraso: float = Field(default=150.0, ge=0.0)
    janela_limite_min: float = Field(default=45.0, ge=1.0)

class DecisaoEconomicaRequest(BaseModel):
    tenant_id: str = "demo_corp"
    origem_lat: float = Field(..., ge=-90, le=90)
    origem_lon: float = Field(..., ge=-180, le=180)
    destino_lat: float = Field(..., ge=-90, le=90)
    destino_lon: float = Field(..., ge=-180, le=180)
    precipitacao_mm: float = Field(default=60.0, ge=0.0, le=250.0)
    parametros: ParametrosDecisaoEconomica = ParametrosDecisaoEconomica()