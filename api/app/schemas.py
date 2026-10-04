from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

ClasseRisco = Literal["critico", "alto", "medio", "baixo"]

class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: Any

class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: Dict[str, Any]

class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]

class TrechoDetalhe(BaseModel):
    id_trecho: int
    nome: Optional[str] = None
    ivi: float = Field(..., ge=0, le=100)
    classe_risco: Optional[str] = None
    altitude_media: Optional[float] = None
    classe_declividade: Optional[float] = None
    distancia_agua_m: Optional[float] = None
    total_alagamentos: Optional[int] = 0
    id_setor_ibge: Optional[str] = None

class ResumoEstatisticas(BaseModel):
    total_trechos: int
    criticos: int
    altos: int
    medios: int
    baixos: int
    ivi_medio: float
