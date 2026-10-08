CREATE TABLE IF NOT EXISTS pracas_pedagio (
    id SERIAL PRIMARY KEY,
    rodovia VARCHAR(30) NOT NULL,
    km NUMERIC(6,1) NOT NULL,
    municipio VARCHAR(80) NOT NULL,
    concessionaria VARCHAR(60) NOT NULL,
    tarifa_base_eixo NUMERIC(8,2) NOT NULL,
    tarifa_vuc NUMERIC(8,2) NOT NULL,
    tarifa_truck_3eixos NUMERIC(8,2) NOT NULL,
    tarifa_carreta_5eixos NUMERIC(8,2) NOT NULL,
    geom GEOMETRY(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pracas_pedagio_geom ON pracas_pedagio USING GIST(geom);

TRUNCATE TABLE pracas_pedagio RESTART IDENTITY CASCADE;

INSERT INTO pracas_pedagio (rodovia, km, municipio, concessionaria, tarifa_base_eixo, tarifa_vuc, tarifa_truck_3eixos, tarifa_carreta_5eixos, geom)
VALUES 
    ('SP-310', 217.0, 'Itirapina', 'EcoNoroeste', 8.90, 8.90, 26.70, 44.50, ST_SetSRID(ST_Point(-47.8242, -22.2530), 4326)),
    ('SP-310', 181.0, 'Rio Claro', 'EcoNoroeste', 6.40, 6.40, 19.20, 32.00, ST_SetSRID(ST_Point(-47.6105, -22.4280), 4326)),
    ('SP-330', 147.0, 'Limeira', 'Autoban', 8.20, 8.20, 24.60, 41.00, ST_SetSRID(ST_Point(-47.3850, -22.6050), 4326)),
    ('SP-348', 77.0, 'Itupeva', 'Autoban', 12.10, 12.10, 36.30, 60.50, ST_SetSRID(ST_Point(-47.0610, -23.1520), 4326)),
    ('SP-348', 36.0, 'Caieiras', 'Autoban', 11.50, 11.50, 34.50, 57.50, ST_SetSRID(ST_Point(-46.8120, -23.3640), 4326));