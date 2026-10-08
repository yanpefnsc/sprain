ALTER TABLE veiculos ADD COLUMN IF NOT EXISTS tenant_id varchar(50) NOT NULL DEFAULT 'demo_corp';
ALTER TABLE operacoes ADD COLUMN IF NOT EXISTS tenant_id varchar(50) NOT NULL DEFAULT 'demo_corp';
ALTER TABLE cenarios_clima ADD COLUMN IF NOT EXISTS tenant_id varchar(50) NOT NULL DEFAULT 'demo_corp';
ALTER TABLE recomendacoes_operacao ADD COLUMN IF NOT EXISTS tenant_id varchar(50) NOT NULL DEFAULT 'demo_corp';
CREATE INDEX IF NOT EXISTS idx_veiculos_tenant ON veiculos (tenant_id);
CREATE INDEX IF NOT EXISTS idx_operacoes_tenant ON operacoes (tenant_id);