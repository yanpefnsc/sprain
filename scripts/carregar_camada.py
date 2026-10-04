"""Carrega um arquivo geoespacial (shp, gpkg, geojson, zip) no PostGIS.

Exemplo:
    python scripts/carregar_camada.py dados/brutos/logradouro.zip trechos_bruto
"""
import argparse
import os
import sys

import geopandas as gpd
from sqlalchemy import create_engine

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")
CRS_PROJETO = 31983  # SIRGAS 2000 / UTM 23S


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arquivo")
    ap.add_argument("tabela")
    ap.add_argument("--substituir", action="store_true", help="apaga a tabela se ela já existir")
    args = ap.parse_args()

    camada = gpd.read_file(args.arquivo)
    print(f"lidas {len(camada)} feições, CRS original: {camada.crs}")

    if camada.crs is None:
        sys.exit("O arquivo veio sem CRS. Descubra qual é (QGIS mostra) antes de carregar.")

    camada = camada.to_crs(CRS_PROJETO)
    camada.columns = [c.lower() for c in camada.columns]
    camada = camada.rename_geometry("geom")
    print("colunas:", [c for c in camada.columns if c != "geom"])
    print("tipo de geometria:", camada.geom_type.unique())

    motor = create_engine(URL_BANCO)
    camada.to_postgis(
        args.tabela,
        motor,
        if_exists="replace" if args.substituir else "fail",
        index=False,
    )
    print(f"tabela '{args.tabela}' gravada.")


if __name__ == "__main__":
    main()
