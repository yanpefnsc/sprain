import os
from typing import cast
import geopandas as gpd
import osmnx as ox
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    print("Obtendo limites de Itaquera...")
    distrito = gpd.read_postgis("SELECT geom FROM distrito_itaquera", motor, geom_col="geom")
    poligono_wgs84 = cast(Polygon | MultiPolygon, distrito.to_crs(4326).union_all())

    print("Baixando malha viaria do OpenStreetMap...")
    grafo = ox.graph_from_polygon(poligono_wgs84, network_type="drive")
    _, edges = ox.graph_to_gdfs(grafo)

    edges_utm = edges.to_crs(31983).reset_index()
    edges_utm["id_trecho"] = edges_utm.index + 1

    colunas = [c for c in ["id_trecho", "name", "highway", "length", "geometry"] if c in edges_utm.columns]
    gdf_final = edges_utm[colunas].copy()

    print("Gravando malha viaria na tabela trechos_osm...")
    gdf_final.to_postgis("trechos_osm", motor, if_exists="replace", index=False)

    print("Concluido com sucesso!")

if __name__ == "__main__":
    main()
