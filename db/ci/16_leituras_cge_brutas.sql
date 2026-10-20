CREATE TABLE IF NOT EXISTS leituras_cge_brutas (
    id_estacao TEXT NOT NULL REFERENCES estacoes_meteorologicas(id_estacao) ON DELETE CASCADE,
    coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    periodo_atual_mm NUMERIC(7,2) NOT NULL CHECK (periodo_atual_mm >= 0),
    periodo_anterior_mm NUMERIC(7,2) NOT NULL CHECK (periodo_anterior_mm >= 0),
    horario_zeramento TIME,
    PRIMARY KEY (id_estacao, coletado_em)
);
