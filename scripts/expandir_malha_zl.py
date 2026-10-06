import os
import geopandas as gpd
import osmnx as ox
from sqlalchemy import create_engine

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

DISTRITOS_ALVO = [
    "ITAQUERA",
    "ARTUR ALVIM",
    "PENHA",
    "SAO MATEUS",
    "GUAIANASES",
    "CIDADE LIDER",
    "PARQUE DO CARMO",
    "VILA MATILDE",
    "PONTE RASA"
]

def main():
    motor = create_engine(URL_BANCO)

    print("Carregando limites distritais a partir do shapefile...")
    gdf_distritos = gpd.read_file("dados/brutos/distrito_municipal_v2/distrito_municipal_v2.shp")
    
    filtro = gdf_distritos["nm_distrit"].str.upper().isin(DISTRITOS_ALVO)
    gdf_area = gdf_distritos[filtro]
    print(f"Distritos selecionados ({len(gdf_area)}): {gdf_area['nm_distrit'].tolist()}")

    print("Unificando poligono e convertendo para WGS84 (EPSG:4326)...")
    poligono_wgs84 = gdf_area.to_crs(4326).union_all()

    print("Baixando malha viaria veicular do OpenStreetMap via OSMnx...")
    grafo = ox.graph_from_polygon(poligono_wgs84, network_type="drive")
    _, edges = ox.graph_to_gdfs(grafo)
    print(f"Total de trechos baixados: {len(edges)}")

    print("Reprojetando para SIRGAS 2000 / UTM 23S (EPSG:31983)...")
    edges_utm = edges.to_crs(31983).reset_index()
    edges_utm["id_trecho"] = edges_utm.index + 1

    colunas = [c for c in ["id_trecho", "name", "highway", "length", "geometry"] if c in edges_utm.columns]
    gdf_final = edges_utm[colunas].copy()

    print("Salvando malha viaria expandida na tabela trechos_osm...")
    gdf_final.to_postgis("trechos_osm", motor, if_exists="replace", index=False)

    print("Criando indices espaciais GIST...")
    with motor.begin() as conn:
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_trechos_osm_geometry ON trechos_osm USING gist (geometry);")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS trechos_osm_id_trecho_idx ON trechos_osm (id_trecho);")

    print("Malha viaria expandida gravada com sucesso!")

if __name__ == "__main__":
    main()
