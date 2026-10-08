CREATE TABLE IF NOT EXISTS veiculos (
    id_veiculo VARCHAR(50) PRIMARY KEY,
    placa VARCHAR(10) NOT NULL,
    modelo VARCHAR(50) NOT NULL,
    tipo_veiculo VARCHAR(20) DEFAULT 'VUC',
    lat_atual DOUBLE PRECISION,
    lon_atual DOUBLE PRECISION,
    status VARCHAR(20) DEFAULT 'DISPONIVEL',
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS operacoes (
    id_operacao VARCHAR(50) PRIMARY KEY,
    id_veiculo VARCHAR(50) REFERENCES veiculos(id_veiculo) ON DELETE SET NULL,
    origem_nome VARCHAR(100),
    origem_lat DOUBLE PRECISION NOT NULL,
    origem_lon DOUBLE PRECISION NOT NULL,
    destino_nome VARCHAR(100),
    destino_lat DOUBLE PRECISION NOT NULL,
    destino_lon DOUBLE PRECISION NOT NULL,
    janela_inicio TIMESTAMP NOT NULL,
    janela_fim TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'PLANNED',
    distancia_planejada_km DOUBLE PRECISION DEFAULT 0.0,
    tempo_planejado_min DOUBLE PRECISION DEFAULT 0.0,
    custo_estimado DOUBLE PRECISION DEFAULT 0.0,
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS operacao_rotas_trechos (
    id_operacao VARCHAR(50) REFERENCES operacoes(id_operacao) ON DELETE CASCADE,
    seq INT NOT NULL,
    id_trecho BIGINT NOT NULL,
    PRIMARY KEY (id_operacao, seq)
);

CREATE TABLE IF NOT EXISTS cenarios_clima (
    id_cenario VARCHAR(50) PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    precipitacao_mm DOUBLE PRECISION NOT NULL,
    janela_horas INT DEFAULT 24,
    tipo VARCHAR(20) DEFAULT 'SIMULACAO',
    gerado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recomendacoes_operacao (
    id_recomendacao SERIAL PRIMARY KEY,
    id_operacao VARCHAR(50) REFERENCES operacoes(id_operacao) ON DELETE CASCADE,
    id_cenario VARCHAR(50) REFERENCES cenarios_clima(id_cenario) ON DELETE CASCADE,
    tipo_acao VARCHAR(30) NOT NULL,
    nivel_risco VARCHAR(20) NOT NULL,
    motivo TEXT NOT NULL,
    confianca DOUBLE PRECISION DEFAULT 0.85,
    km_adicionais DOUBLE PRECISION DEFAULT 0.0,
    minutos_adicionais DOUBLE PRECISION DEFAULT 0.0,
    custo_desvio DOUBLE PRECISION DEFAULT 0.0,
    prejuizo_potencial_evitado DOUBLE PRECISION DEFAULT 0.0,
    rota_alternativa_geojson JSONB,
    gerado_em TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operacoes_status ON operacoes(status);
CREATE INDEX IF NOT EXISTS idx_recomendacoes_op ON recomendacoes_operacao(id_operacao);
