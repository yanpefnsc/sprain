CREATE TABLE IF NOT EXISTS public.webhooks_tenant (
    tenant_id text PRIMARY KEY,
    url text NOT NULL,
    secret_cifrado text NOT NULL,
    eventos text[] NOT NULL DEFAULT '{}',
    atualizado_em timestamp with time zone NOT NULL DEFAULT now()
);
