import re
import unicodedata

BLOQUEIO = ["intransitavel", "alagada", "alagamento", "bloqueada", "fechada", "submersa", "interditada"]
LIBERADA = ["liberada", "liberado", "transitavel", "normalizada", "escoou"]
GRAVES = ["totalmente", "grave", "intransitavel", "critico"]

PADRAO_VIA = re.compile(
    r"\b(?:avenida|av\.?|rua|r\.|alameda|al\.|rodovia|estrada)\s+"
    r"([a-z0-9\s\-]+?)"
    r"(?=\s+(?:na altura|proximo|esquina|com|totalmente|alagada|bloqueada|interditada|intransitavel|fechada|submersa)|[,.;]|\s*$)"
)


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def extrair_dados_ocorrencia(texto: str) -> dict:
    t = sem_acento(texto)

    # bloqueio primeiro: "intransitavel" contem "transitavel"
    if any(p in t for p in BLOQUEIO):
        status = "INTRANSITAVEL"
        severidade = "VERMELHO" if any(p in t for p in GRAVES) else "LARANJA"
    elif any(p in t for p in LIBERADA):
        status = "TRANSITAVEL"
        severidade = "VERDE"
    else:
        status = None
        severidade = None

    achou = PADRAO_VIA.search(t)
    via = achou.group(1).strip() if achou else None

    return {"via": via, "status": status, "severidade": severidade}