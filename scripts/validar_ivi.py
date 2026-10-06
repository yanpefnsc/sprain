import os
import re
import sys
import unicodedata

import pandas as pd
from sqlalchemy import create_engine

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")
CSV_PADRAO = r"C:\Users\Win11\Desktop\importante\flood-fusion-sp\data\processed\cge_itaquera.csv"

IGNORAR = {"rua", "avenida", "estrada", "travessa", "alameda", "praca", "viaduto", "rod", "est", "dos", "das"}


def limpar(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def palavras_chave(via):
    return [p for p in limpar(via).split() if len(p) > 2 and p not in IGNORAR]


def achar_trechos(trechos, chaves):
    conjunto = set(chaves)
    palavras = trechos["nome_limpo"].map(lambda n: {p for p in n.split() if len(p) > 2 and p not in IGNORAR})
    igual = trechos[palavras.map(lambda p: p == conjunto)]
    if not igual.empty:
        return igual
    return trechos[palavras.map(lambda p: len(p) >= 2 and p <= conjunto)]


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else CSV_PADRAO
    eventos = pd.read_csv(caminho)
    eventos = eventos[eventos["status_intransitabilidade"].str.contains("Intransit", na=False)]
    vias = eventos["via_registrada"].drop_duplicates().tolist()

    motor = create_engine(URL_BANCO)
    trechos = pd.read_sql("SELECT id_trecho, name, ivi_score, classe_risco FROM trechos_osm WHERE name IS NOT NULL", motor)
    trechos["nome_limpo"] = trechos["name"].map(limpar)
    todos = pd.read_sql("SELECT ivi_score, classe_risco FROM trechos_osm", motor)

    achados = []
    print(f"{len(vias)} vias intransitaveis no CSV\n")
    for via in vias:
        chaves = palavras_chave(via)
        casou = achar_trechos(trechos, chaves)
        if casou.empty:
            print(f"- {via}: NENHUM trecho encontrado (chaves: {chaves})")
            continue
        achados.append(casou)
        print(f"- {via}: {len(casou)} trechos | IVI medio {casou['ivi_score'].mean():.1f} | maximo {casou['ivi_score'].max():.1f}")

    if not achados:
        print("\nNada casou. Confira os nomes das vias.")
        return

    casados = pd.concat(achados).drop_duplicates("id_trecho")
    alto = ["Alto", "Critico"]
    print("\n--- resumo ---")
    print(f"trechos casados: {len(casados)} de {len(todos)} no banco")
    print(f"IVI medio dos casados: {casados['ivi_score'].mean():.1f} | da malha toda: {todos['ivi_score'].mean():.1f}")
    print(f"% em Alto/Critico nos casados: {casados['classe_risco'].isin(alto).mean() * 100:.0f}% | na malha toda: {todos['classe_risco'].isin(alto).mean() * 100:.0f}%")


if __name__ == "__main__":
    main()