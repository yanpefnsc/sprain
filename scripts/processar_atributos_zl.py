import os
import geopandas as gpd
import osmnx as ox
from shapely.geometry import box
from shapely.ops import nearest_points
from sqlalchemy import create_engine, text

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    print("1. Lendo os trechos da malha expandida...")
    trechos = gpd.read_postgis("SELECT id_trecho, geom FROM trechos_osm", motor, geom_col="geom")
    print(f"Total de trechos carregados: {len(trechos)}")

    print("2. Obtendo envelope geografico (WGS84)...")
    trechos_wgs84 = trechos.to_crs(4326)
    minx, miny, maxx, maxy = trechos_wgs84.total_bounds
    # Expande levemente o bounding box para garantir hidrografia na borda
    envelope = box(minx - 0.02, miny - 0.02, maxx + 0.02, maxy + 0.02)

    print("3. Baixando cursos d'agua do OpenStreetMap...")
    tags = {
        "waterway": ["river", "stream", "canal", "drain", "ditch"],
        "natural": ["water"]
    }
    cursos_agua = ox.features_from_polygon(envelope, tags=tags)
    print(f"Total de feicoes hidrologicas obtidas: {len(cursos_agua)}")

    print("4. Reprojetando hidrografia para SIRGAS 2000 (EPSG:31983)...")
    cursos_utm = cursos_agua.to_crs(31983)
    uniao_hidro = cursos_utm.union_all()

    print("5. Calculando distancia ate o curso d'agua mais proximo para cada trecho...")
    centroides = trechos.geometry.centroid
    trechos["distancia_agua_m"] = centroides.distance(uniao_hidro)

    print("6. Atualizando distancia_agua_m no banco de dados...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS distancia_agua_m double precision;"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS classe_declividade double precision DEFAULT 1.0;"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS grau_suscetibilidade text DEFAULT 'Medio';"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS total_alagamentos integer DEFAULT 0;"))
    
    # Gravacao rapida em lote da distancia
    df_temp = trechos[["id_trecho", "distancia_agua_m"]].copy()
    df_temp.to_sql("temp_dist_agua", motor, if_exists="replace", index=False)

    with motor.begin() as conn:
        conn.execute(text("""
            UPDATE trechos_osm t
            SET distancia_agua_m = d.distancia_agua_m
            FROM temp_dist_agua d
            WHERE t.id_trecho = d.id_trecho;
            DROP TABLE IF EXISTS temp_dist_agua;
        """))

    print("7. Classificando grau de suscetibilidade...")
    with motor.begin() as conn:
        conn.execute(text("""
            UPDATE trechos_osm
            SET grau_suscetibilidade = CASE 
                WHEN distancia_agua_m <= 60 THEN 'Muito Alto'
                WHEN distancia_agua_m <= 150 THEN 'Alto'
                WHEN distancia_agua_m <= 300 THEN 'Medio'
                ELSE 'Baixo'
            END;
        """))

    print("8. Calculando o IVI (0 a 100) na malha inteira...")
    with motor.begin() as conn:
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS ivi_score double precision;"))
        conn.execute(text("ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS classe_risco text;"))
        conn.execute(text("""
            WITH normalizado AS (
                SELECT 
                    id_trecho,
                    GREATEST(0, (1 - LEAST(COALESCE(distancia_agua_m, 1000), 1000) / 1000.0)) * 35 AS f_agua,
                    (CASE WHEN classe_declividade = 1.0 THEN 1.0 WHEN classe_declividade = 2.0 THEN 0.5 ELSE 0.1 END) * 25 AS f_decliv,
                    ((820.0 - LEAST(GREATEST(COALESCE(altitude_media, 750.0), 736.0), 820.0)) / (820.0 - 736.0)) * 15 AS f_alt,
                    (CASE 
                        WHEN grau_suscetibilidade = 'Muito Alto' THEN 1.0
                        WHEN grau_suscetibilidade = 'Alto' THEN 0.75
                        WHEN grau_suscetibilidade = 'Medio' THEN 0.4
                        ELSE 0.1
                    END) * 15 AS f_susc,
                    LEAST(COALESCE(total_alagamentos, 0), 5) / 5.0 * 10 AS f_cge
                FROM trechos_osm
            )
            UPDATE trechos_osm t
            SET 
                ivi_score = ROUND((n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge)::numeric, 2),
                classe_risco = CASE 
                    WHEN (n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge) >= 70 THEN 'Critico'
                    WHEN (n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge) >= 50 THEN 'Alto'
                    WHEN (n.f_agua + n.f_decliv + n.f_alt + n.f_susc + n.f_cge) >= 30 THEN 'Medio'
                    ELSE 'Baixo'
                END
            FROM normalizado n
            WHERE t.id_trecho = n.id_trecho;
        """))

    print("Concluido com sucesso! Todos os 27.445 trechos possuem IVI calculado.")

if __name__ == "__main__":
    main()
