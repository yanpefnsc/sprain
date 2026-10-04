import os
import geobr
import geopandas as gpd
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    print("1. Obtendo limites de Itaquera...")
    distrito = gpd.read_postgis("SELECT geom FROM distrito_itaquera", motor, geom_col="geom")

    print("2. Baixando e recortando setores censitarios do IBGE...")
    setores_sp = geobr.read_census_tract(code_tract=3550308, year=2010)
    setores_sp = setores_sp.to_crs(31983)
    setores_itaquera = gpd.sjoin(setores_sp, distrito, predicate="intersects").drop(columns=["index_right"])

    col_id = [c for c in ["code_tract", "cd_geocod", "cd_setor"] if c in setores_itaquera.columns][0]
    setores_final = setores_itaquera[[col_id, "geometry"]].rename(columns={col_id: "id_setor"}).copy()

    print(f"3. Gravando {len(setores_final)} setores censitarios reais no banco...")
    setores_final.to_postgis("setores_ibge_itaquera", motor, if_exists="replace", index=False)

    print("4. Atualizando colunas e associando dados territoriais aos trechos...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE setores_ibge_itaquera RENAME COLUMN geometry TO geom;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ibge_geom ON setores_ibge_itaquera USING GIST (geom);"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS grau_suscetibilidade text DEFAULT 'Baixo';"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS id_setor_ibge text;"))

        # Associa o setor censitario a cada rua
        conn.execute(text("""
            UPDATE trechos_osm t
            SET id_setor_ibge = sub.id_setor::text
            FROM (
                SELECT DISTINCT ON (t_in.id_trecho) t_in.id_trecho, s.id_setor
                FROM trechos_osm t_in
                JOIN setores_ibge_itaquera s ON ST_Intersects(t_in.geom, s.geom)
            ) sub
            WHERE t.id_trecho = sub.id_trecho;
        """))

        # Classificacao da suscetibilidade fisica
        conn.execute(text("""
            UPDATE trechos_osm
            SET grau_suscetibilidade = CASE 
                WHEN distancia_agua_m <= 60 AND classe_declividade = 1.0 THEN 'Muito Alto'
                WHEN distancia_agua_m <= 120 OR classe_declividade = 1.0 THEN 'Alto'
                WHEN distancia_agua_m <= 250 THEN 'Medio'
                ELSE 'Baixo'
            END;
        """))

    print("Passo 5 finalizado com sucesso com dados oficiais do IBGE!")

if __name__ == "__main__":
    main()
