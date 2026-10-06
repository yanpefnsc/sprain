import os
import sys
import requests
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    pasta_cge = os.path.join("dados", "brutos", "cge")
    os.makedirs(pasta_cge, exist_ok=True)
    caminho_csv = os.path.join(pasta_cge, "pontos_alagamento_cge.csv")

    print("1. Lendo historico de alagamentos CGE-SP...")
    if not os.path.exists(caminho_csv) or os.path.getsize(caminho_csv) == 0:
        sys.exit(f"Sem dados do CGE em {caminho_csv}. Coloque o CSV real do historico (com colunas de latitude e longitude) nesse caminho e rode de novo.")

    df = pd.read_csv(caminho_csv)
    col_lat = [c for c in df.columns if "lat" in c.lower()][0]
    col_lon = [c for c in df.columns if "lon" in c.lower()][0]
    df = df.dropna(subset=[col_lat, col_lon])

    gdf_pontos = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[col_lon], df[col_lat]),
        crs="EPSG:4326"
    ).to_crs(31983)

    print("2. Recortando pontos para Itaquera...")
    distrito = gpd.read_postgis("SELECT geom FROM distrito_itaquera", motor, geom_col="geom")
    pontos_itaquera = gpd.sjoin(gdf_pontos, distrito, predicate="intersects").drop(columns=["index_right"])

    colunas = [c for c in ["data", "local", "tipo", "geometry"] if c in pontos_itaquera.columns]
    gdf_final = pontos_itaquera[colunas].copy()

    print(f"3. Gravando {len(gdf_final)} ocorrencias na tabela alagamentos_cge...")
    gdf_final.to_postgis("alagamentos_cge", motor, if_exists="replace", index=False)

    print("4. Associando alagamentos aos trechos viarios...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE alagamentos_cge RENAME COLUMN geometry TO geom;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alagamentos_geom ON alagamentos_cge USING GIST (geom);"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS total_alagamentos integer DEFAULT 0;"))
        conn.execute(text("""
            UPDATE trechos_osm t
            SET total_alagamentos = sub.total
            FROM (
                SELECT t_in.id_trecho, COUNT(a.geom) AS total
                FROM trechos_osm t_in
                LEFT JOIN alagamentos_cge a ON ST_DWithin(t_in.geom, a.geom, 50)
                GROUP BY t_in.id_trecho
            ) sub
            WHERE t.id_trecho = sub.id_trecho;
        """))

    print("Passo 6 concluido com sucesso!")

if __name__ == "__main__":
    main()
