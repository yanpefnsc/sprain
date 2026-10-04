import os
import folium
import geopandas as gpd
from sqlalchemy import create_engine

URL_BANCO = os.getenv("URL_BANCO", "postgresql+psycopg2://enchentes:enchentes@localhost:5432/enchentes")

def main():
    motor = create_engine(URL_BANCO)

    print("Carregando trechos do PostGIS...")
    sql = "SELECT id_trecho, name, ivi_score, classe_risco, distancia_agua_m, altitude_media, geom FROM trechos_osm"
    trechos = gpd.read_postgis(sql, motor, geom_col="geom").to_crs(4326)

    centro_lat = trechos.geometry.centroid.y.mean()
    centro_lon = trechos.geometry.centroid.x.mean()

    # Esri WorldStreetMap: Não exige API Key, não exige Referer e funciona perfeito em arquivos locais file://
    mapa = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=14,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom, 2012"
    )

    cores = {
        "Critico": "#d90429",
        "Alto": "#f77f00",
        "Medio": "#fcbf49",
        "Baixo": "#2b9348"
    }

    print("Desenhando trechos viarios...")
    for _, row in trechos.iterrows():
        cor = cores.get(row["classe_risco"], "#808080")
        peso = 4.5 if row["classe_risco"] == "Critico" else 2.5
        
        info = (
            f"<b>Rua:</b> {row['name'] or 'Sem nome'}<br>"
            f"<b>Risco:</b> {row['classe_risco']}<br>"
            f"<b>Score IVI:</b> {row['ivi_score']}<br>"
            f"<b>Dist. Rio:</b> {round(row['distancia_agua_m'], 1) if row['distancia_agua_m'] else '-'} m<br>"
            f"<b>Altitude:</b> {round(row['altitude_media'], 1) if row['altitude_media'] else '-'} m"
        )
        
        folium.GeoJson(
            row["geom"],
            style_function=lambda x, c=cor, p=peso: {"color": c, "weight": p, "opacity": 0.85},
            tooltip=folium.Tooltip(info)
        ).add_to(mapa)

    legenda_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000; background: white;
                padding: 12px 18px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-size: 13px; font-family: sans-serif;">
        <h4 style="margin: 0 0 8px 0; font-size: 14px;">Índice de Intransitabilidade (IVI)</h4>
        <div><span style="background: #d90429; width: 14px; height: 14px; display: inline-block; margin-right: 6px; border-radius: 2px;"></span><b>Crítico</b> (Score ≥ 70)</div>
        <div><span style="background: #f77f00; width: 14px; height: 14px; display: inline-block; margin-right: 6px; border-radius: 2px;"></span><b>Alto</b> (50 - 69)</div>
        <div><span style="background: #fcbf49; width: 14px; height: 14px; display: inline-block; margin-right: 6px; border-radius: 2px;"></span><b>Médio</b> (30 - 49)</div>
        <div><span style="background: #2b9348; width: 14px; height: 14px; display: inline-block; margin-right: 6px; border-radius: 2px;"></span><b>Baixo</b> (&lt; 30)</div>
    </div>
    """
    mapa.get_root().html.add_child(folium.Element(legenda_html))

    caminho_mapa = "dados/processados/mapa_vulnerabilidade.html"
    mapa.save(caminho_mapa)
    print("Mapa limpo gerado com sucesso!")

if __name__ == "__main__":
    main()
