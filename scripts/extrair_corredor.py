import os
import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine

# Utiliza espelho alternativo com maior capacidade
ox.settings.overpass_endpoint = "https://overpass.kumi.systems/api/interpreter"
ox.settings.timeout = 180

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def extrair_por_rodovia(motor):
    print("Baixando eixos das rodovias SP-310, SP-330 e SP-348...")
    
    # Query estruturada direta nas relacoes/vias do estado de SP
    filtro = '["ref"~"SP-310|SP-330|SP-348"]["highway"~"motorway|trunk|primary"]'
    
    # Consulta restrita a Sao Paulo
    try:
        grafo = ox.graph_from_place("São Paulo state, Brazil", network_type="drive", custom_filter=filtro)
        _, edges = ox.graph_to_gdfs(grafo)
        print(f"Trechos rodoviarios extraidos: {len(edges)} segmentos.")
        
        edges_utm = edges.to_crs(31983).reset_index()
        edges_utm["id_trecho"] = edges_utm.index + 1
        colunas = [c for c in ["id_trecho", "name", "ref", "highway", "length", "geometry"] if c in edges_utm.columns]
        gdf_final = edges_utm[colunas].copy()
        
        gdf_final.to_postgis("corredor_sp_araraquara", motor, if_exists="replace", index=False)
        print("Tabela corredor_sp_araraquara indexada com sucesso no PostGIS!")
    except Exception as e:
        print(f"Falha na consulta por place: {e}. Executando extracao por trechos intermediarios...")
        # Fallback rapido: corredores municipais encadeados
        cidades = ["Araraquara, SP, Brazil", "São Carlos, SP, Brazil", "Rio Claro, SP, Brazil", "Limeira, SP, Brazil", "Campinas, SP, Brazil", "Jundiaí, SP, Brazil"]
        gdfs = []
        for cidade in cidades:
            print(f"Obtendo rodovias em {cidade}...")
            g = ox.graph_from_place(cidade, network_type="drive", custom_filter='["highway"~"motorway|trunk"]')
            _, ed = ox.graph_to_gdfs(g)
            gdfs.append(ed)
        import pandas as pd
        merged = pd.concat(gdfs).drop_duplicates(subset=["geometry"])
        merged_utm = merged.to_crs(31983).reset_index()
        merged_utm["id_trecho"] = merged_utm.index + 1
        colunas = [c for c in ["id_trecho", "name", "highway", "length", "geometry"] if c in merged_utm.columns]
        gdf_final = merged_utm[colunas].copy()
        gdf_final.to_postgis("corredor_sp_araraquara", motor, if_exists="replace", index=False)
        print(f"Tabela corredor_sp_araraquara gravada via fallback com {len(gdf_final)} segmentos!")

def main():
    motor = create_engine(URL_BANCO)
    extrair_por_rodovia(motor)

if __name__ == "__main__":
    main()