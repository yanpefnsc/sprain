from pydantic import BaseModel, Field
from typing import Optional, Dict

class AlertaRapidoCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    nivel: str = Field(..., pattern="^(VERDE|AMARELO|LARANJA|VERMELHO)$")
    corporacao: str = Field(default="DEFESA_CIVIL")
    observacao: Optional[str] = None

class OcorrenciaTextoCreate(BaseModel):
    texto: str
    fonte: str = "OPERACIONAL"

class ResumoEstatisticas(BaseModel):
    total_trechos: int
    trechos_criticos: int
    trechos_interditados: int
    distribuicao_severidade: Dict[str, int]
