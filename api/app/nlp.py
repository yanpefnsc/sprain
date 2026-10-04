import re
from typing import Dict, Any, List

PREFIXOS = r"(?:rua|r\.|av\.|avenida|travessa|tv\.|estrada|estr\.|alameda|al\.)"
STOPWORDS_VIAS = {
    "totalmente", "parcialmente", "completamente", "muito", "alagada", 
    "alagado", "intransitavel", "bloqueada", "bloqueado", "interditada",
    "parada", "parado", "na", "no", "em", "altura", "proximo", "próximo",
    "sentido", "perto", "esquina", "devido"
}

PADRAO_PREFIXO = re.compile(
    rf"\b({PREFIXOS}\s+[A-Za-zÀ-ÿ0-9\s'-]+)",
    re.IGNORECASE
)

TERMOS_INTRANSITAVEL = [
    "intransitavel", "intransitável", "bloqueada", "bloqueado", 
    "alagada", "alagado", "alagamento", "parada", "parado", 
    "subiu a agua", "subiu a água", "interditada", "interditado"
]
TERMOS_TRANSITAVEL = [
    "liberada", "liberado", "transitavel", "transitável", 
    "normalizada", "normalizado", "escoou", "desobstruida", "desobstruído"
]

def limpar_nome_via(candidato: str) -> str:
    palavras = candidato.strip().split()
    resultado = []
    for i, p in enumerate(palavras):
        p_clean = re.sub(r"[^\wÀ-ÿ-]", "", p.lower())
        if i > 0 and p_clean in STOPWORDS_VIAS:
            break
        resultado.append(p)
    return " ".join(resultado).strip()

def extrair_logradouros_e_status(texto: str) -> Dict[str, Any]:
    texto_limpo = texto.strip()
    texto_lower = texto_limpo.lower()
    
    status = "ALERTA"
    if any(termo in texto_lower for termo in TERMOS_INTRANSITAVEL):
        status = "INTRANSITAVEL"
    elif any(termo in texto_lower for termo in TERMOS_TRANSITAVEL):
        status = "TRANSITAVEL"

    vias: List[str] = []
    for match in PADRAO_PREFIXO.finditer(texto_limpo):
        bruto = match.group(1)
        nome_tratado = limpar_nome_via(bruto)
        if len(nome_tratado.split()) >= 2:
            vias.append(nome_tratado)

    return {
        "status": status,
        "candidatos_vias": list(set(vias))
    }
