DO $$
DECLARE
    i INT;
    v_orig BIGINT;
    v_dest BIGINT;
    v_orig_pt geometry;
    v_dest_pt geometry;
    v_orig_name TEXT;
    v_dest_name TEXT;
    v_op_id VARCHAR(50);
    v_trk_id VARCHAR(50);
    v_dist_km FLOAT;
    v_tempo_min FLOAT;
    v_custo FLOAT;
    v_seq INT;
    v_edge BIGINT;
    v_geom_srid INT;
BEGIN
    SELECT ST_SRID(the_geom) INTO v_geom_srid FROM trechos_osm_vertices_pgr LIMIT 1;
    IF v_geom_srid IS NULL THEN
        v_geom_srid := 4326;
    END IF;

    FOR i IN 1..50 LOOP
        INSERT INTO veiculos (id_veiculo, placa, modelo, tipo_veiculo, lat_atual, lon_atual)
        VALUES (
            'TRK-' || LPAD(i::text, 3, '0'),
            'BRA' || LPAD(i::text, 2, '0') || '9' || (i % 10)::text,
            'Mercedes Accelo ' || ((i % 5) + 8)::text || '15',
            (ARRAY['VUC', 'TOCO', 'VAN', 'CARRETA'])[(i % 4) + 1],
            -23.542,
            -46.468
        )
        ON CONFLICT (id_veiculo) DO NOTHING;
    END LOOP;

    FOR i IN 1..100 LOOP
        v_op_id := 'OP-' || LPAD(i::text, 3, '0');
        v_trk_id := 'TRK-' || LPAD(((i % 50) + 1)::text, 3, '0');

        SELECT id, the_geom INTO v_orig, v_orig_pt
        FROM trechos_osm_vertices_pgr
        ORDER BY RANDOM() LIMIT 1;

        SELECT id, the_geom INTO v_dest, v_dest_pt
        FROM trechos_osm_vertices_pgr
        WHERE id != v_orig
        ORDER BY RANDOM() LIMIT 1;

        SELECT 
            COALESCE(SUM(ST_Length(t.geom)) / 1000.0, 5.0),
            COALESCE(SUM(ST_Length(t.geom) / 1000.0 / 30.0 * 60.0), 12.0)
        INTO v_dist_km, v_tempo_min
        FROM pgr_dijkstra(
            'SELECT id_trecho AS id, source::bigint, target::bigint, ST_Length(geom) AS cost, ST_Length(geom) AS reverse_cost FROM trechos_osm WHERE source IS NOT NULL AND target IS NOT NULL',
            v_orig, v_dest, directed := false
        ) d
        JOIN trechos_osm t ON t.id_trecho = d.edge
        WHERE d.edge != -1;

        v_custo := ROUND(((v_dist_km * 4.50) + (v_tempo_min / 60.0 * 85.0))::numeric, 2);

        INSERT INTO operacoes (
            id_operacao, id_veiculo, origem_nome, origem_lat, origem_lon,
            destino_nome, destino_lat, destino_lon, janela_inicio, janela_fim,
            status, distancia_planejada_km, tempo_planejado_min, custo_estimado
        ) VALUES (
            v_op_id, v_trk_id,
            'Polo Logístico ' || i::text,
            ROUND(ST_Y(ST_Transform(v_orig_pt, 4326))::numeric, 6),
            ROUND(ST_X(ST_Transform(v_orig_pt, 4326))::numeric, 6),
            'Destinatário ' || i::text,
            ROUND(ST_Y(ST_Transform(v_dest_pt, 4326))::numeric, 6),
            ROUND(ST_X(ST_Transform(v_dest_pt, 4326))::numeric, 6),
            NOW() + (i || ' hours')::interval,
            NOW() + ((i + 4) || ' hours')::interval,
            'PLANNED',
            ROUND(v_dist_km::numeric, 2),
            ROUND(v_tempo_min::numeric, 1),
            v_custo
        )
        ON CONFLICT (id_operacao) DO NOTHING;

        INSERT INTO operacao_rotas_trechos (id_operacao, seq, id_trecho)
        SELECT v_op_id, d.seq, d.edge
        FROM pgr_dijkstra(
            'SELECT id_trecho AS id, source::bigint, target::bigint, ST_Length(geom) AS cost, ST_Length(geom) AS reverse_cost FROM trechos_osm WHERE source IS NOT NULL AND target IS NOT NULL',
            v_orig, v_dest, directed := false
        ) d
        WHERE d.edge != -1
        ON CONFLICT DO NOTHING;
    END LOOP;
END $$;
