CREATE TABLE IF NOT EXISTS leituras_chuva (
    id bigserial PRIMARY KEY,
    posto text NOT NULL,
    periodo_atual_mm numeric(6,1) NOT NULL,
    periodo_anterior_mm numeric(6,1) NOT NULL,
    acumulado_mm numeric(6,1) NOT NULL,
    coletado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_leituras_posto_tempo ON leituras_chuva (posto, coletado_em DESC);

CREATE TABLE IF NOT EXISTS historico_estado (
    id bigserial PRIMARY KEY,
    id_trecho bigint NOT NULL,
    status text NOT NULL,
    severidade text,
    origem text,
    registrado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hist_trecho_tempo ON historico_estado (id_trecho, registrado_em DESC);
CREATE INDEX IF NOT EXISTS idx_hist_tempo ON historico_estado (registrado_em DESC);

CREATE TABLE IF NOT EXISTS snapshots_resumo (
    id bigserial PRIMARY KEY,
    coletado_em timestamptz NOT NULL DEFAULT now(),
    origem text NOT NULL,
    acumulado_mm numeric(6,1) NOT NULL,
    bloqueadas int NOT NULL,
    vermelho int NOT NULL,
    laranja int NOT NULL,
    amarelo int NOT NULL,
    verde int NOT NULL
);

CREATE OR REPLACE FUNCTION registrar_historico_estado() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.status IS NOT DISTINCT FROM OLD.status
       AND NEW.severidade IS NOT DISTINCT FROM OLD.severidade THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'INSERT' AND NEW.status = 'TRANSITAVEL' THEN
        RETURN NEW;
    END IF;
    INSERT INTO historico_estado (id_trecho, status, severidade, origem)
    VALUES (NEW.id_trecho, NEW.status, NEW.severidade, left(NEW.relato_origem, 200));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_historico_estado ON estado_operacional_trechos;
CREATE TRIGGER trg_historico_estado
AFTER INSERT OR UPDATE ON estado_operacional_trechos
FOR EACH ROW EXECUTE FUNCTION registrar_historico_estado();
