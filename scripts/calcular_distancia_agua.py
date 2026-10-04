import os
import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    print("1. A obter o poligono de Itaquera...")
    distrito = gpd.read_postgis("SELECT geom FROM distrito_itaquera", motor, geom_col="geom")
    poligono_wgs84 = distrito.to_crs(4326).union_all()

    print("2. A descarregar hidrografia do OSM...")
    tags = {"waterway": ["river", "stream", "canal", "drain"]}
    cursos_agua = ox.features_from_polygon(poligono_wgs84, tags=tags)

    if cursos_agua.empty:
        print("Nenhum curso de agua encontrado.")
        return

    cursos_agua = cursos_agua.to_crs(31983).reset_index()
    colunas_validas = [c for c in ["name", "waterway", "geometry"] if c in cursos_agua.columns]
    hidro = cursos_agua[colunas_validas].copy()

    print(f"3. A gravar {len(hidro)} elementos em hidrografia_osm...")
    hidro.to_postgis("hidrografia_osm", motor, if_exists="replace", index=False)

    print("4. A calcular a distancia minima de cada rua a agua via PostGIS...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE hidrografia_osm RENAME COLUMN geometry TO geom;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_hidrografia_geom ON hidrografia_osm USING GIST (geom);"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS distancia_agua_m double precision;"))
        conn.execute(text("""
            UPDATE trechos_osm t
            SET distancia_agua_m = sub.dist
            FROM (
                SELECT t_inner.id_trecho,
                       (SELECT ST_Distance(t_inner.geom, h.geom)
                        FROM hidrografia_osm h
                        ORDER BY t_inner.geom <-> h.geom
                        LIMIT 1) as dist
                FROM trechos_osm t_inner
            ) sub
            WHERE t.id_trecho = sub.id_trecho;
        """))

    print("Passo 4 concluido com sucesso!")

if __name__ == "__main__":
    main()
