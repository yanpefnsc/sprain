import os
import urllib.request
import gzip
import shutil
import geopandas as gpd
import rasterio
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    pasta_alt = os.path.join("dados", "brutos", "altitude")
    os.makedirs(pasta_alt, exist_ok=True)
    caminho_hgt = os.path.join(pasta_alt, "S24W047.hgt")

    if not os.path.exists(caminho_hgt):
        print("A descarregar DEM SRTM 30m diretamente da AWS...")
        url = "https://elevation-tiles-prod.s3.amazonaws.com/skadi/S24/S24W047.hgt.gz"
        caminho_gz = caminho_hgt + ".gz"
        urllib.request.urlretrieve(url, caminho_gz)
        with gzip.open(caminho_gz, "rb") as f_in, open(caminho_hgt, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(caminho_gz)
        print("Ficheiro HGT descarregado e descomprimido com sucesso!")

    print("A calcular altitude exata para todos os trechos...")
    trechos = gpd.read_postgis("SELECT id_trecho, geom FROM trechos_osm", motor, geom_col="geom")
    centroides_wgs84 = trechos.geometry.centroid.to_crs(4326)

    pontos = [(p.x, p.y) for p in centroides_wgs84]

    with rasterio.open(caminho_hgt) as src:
        amostras = list(src.sample(pontos))
        altitudes = [float(val[0]) if val[0] > -32768 else None for val in amostras]

    trechos["altitude_media"] = altitudes

    print("A atualizar a base de dados PostGIS...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS altitude_media double precision;"))
        for _, row in trechos.dropna(subset=["altitude_media"]).iterrows():
            conn.execute(
                text("UPDATE trechos_osm SET altitude_media = :alt WHERE id_trecho = :id"),
                {"alt": row["altitude_media"], "id": row["id_trecho"]}
            )

    print("Passo 3 concluido: todas as altitudes foram calculadas e gravadas!")

if __name__ == "__main__":
    main()
