import os
import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)
    print("Baixando eixos viarios principais de Araraquara/SP...")
    gdf = ox.geocode_to_gdf("Araraquara, São Paulo, Brazil")
    poligono = gdf.geometry.iloc[0]
    
    grafo = ox.graph_from_polygon(poligono, network_type="drive", custom_filter='["highway"~"motorway|trunk|primary|secondary"]')
    _, edges = ox.graph_to_gdfs(grafo)
    print(f"Eixos principais obtidos: {len(edges)} trechos.")
    
    edges_utm = edges.to_crs(31983).reset_index()
    edges_utm["id_trecho"] = edges_utm.index + 1
    colunas = [c for c in ["id_trecho", "name", "highway", "length", "geometry"] if c in edges_utm.columns]
    gdf_final = edges_utm[colunas].copy()
    gdf_final.to_postgis("trechos_araraquara", motor, if_exists="replace", index=False)
    print("Tabela trechos_araraquara criada e indexada com sucesso!")

if __name__ == "__main__":
    main()