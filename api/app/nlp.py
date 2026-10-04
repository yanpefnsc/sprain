import re

def extrair_dados_ocorrencia(texto: str) -> dict:
    t = texto.lower()
    status = "INTRANSITAVEL" if any(w in t for w in ["intransitavel", "alagada", "alagamento", "bloqueada", "fechada", "submersa"]) else "TRANSITAVEL"
    severidade = "ALTA" if any(w in t for w in ["totalmente", "grave", "intransitavel", "critico"]) else "MODERADA"
    
    padrao = r'(?:avenida|ave?\.?|rua|r\.|alameda|al\.|rodovia|estrada)\s+([a-zA-Z0-9\s\-]+?)(?=\s+(?:na altura|proximo|esquina|com|totalmente|alagada|bloqueada|$))'
    m = re.search(padrao, texto, re.IGNORECASE)
    via = m.group(1).strip() if m else None
    
    if not via:
        palavras = texto.split()
        if len(palavras) >= 2:
            via = " ".join(palavras[:3])

    return {"via": via, "status": status, "severidade": severidade}
