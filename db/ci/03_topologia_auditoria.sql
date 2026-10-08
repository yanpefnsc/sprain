CREATE EXTENSION IF NOT EXISTS pgrouting;

-- topologia a partir dos nós do OSM (u -> source, v -> target)
ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS source bigint;
ALTER TABLE trechos_osm ADD COLUMN IF NOT EXISTS target bigint;
UPDATE trechos_osm SET source = u, target = v WHERE source IS NULL OR target IS NULL;

CREATE TABLE IF NOT EXISTS trechos_osm_vertices_pgr (
    id bigint PRIMARY KEY,
    the_geom geometry(Point, 31983)
);

INSERT INTO trechos_osm_vertices_pgr (id, the_geom)
SELECT DISTINCT ON (id) id, the_geom
FROM (
    SELECT u AS id, ST_StartPoint(geom) AS the_geom FROM trechos_osm
    UNION ALL
    SELECT v AS id, ST_EndPoint(geom) AS the_geom FROM trechos_osm
) x
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_vertices_pgr_geom ON trechos_osm_vertices_pgr USING gist (the_geom);
CREATE INDEX IF NOT EXISTS idx_trechos_osm_source ON trechos_osm (source);
CREATE INDEX IF NOT EXISTS idx_trechos_osm_target ON trechos_osm (target);

CREATE TABLE IF NOT EXISTS auditoria_previsao_realidade (
    id serial PRIMARY KEY,
    criado_em timestamptz DEFAULT now(),
    resultado_classificacao text
);