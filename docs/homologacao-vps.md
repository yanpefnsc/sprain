# Homologação em uma VPS Linux

Este roteiro prepara o acesso externo à API pelo Caddy e o serviço de coleta de
chuva. Ele ainda precisa ser executado em uma VPS com domínio real antes de ser
considerado homologado. Não use um banco ou credenciais de produção para ensaios.

O CI também sobe `docker-compose.prod.yml` com `compose.vps.yml` em um runner
Linux descartável, gera chaves de ensaio, confirma que o banco nasce sem a carga
de demonstração, aplica os arquivos `db/ci` somente nesse runner e verifica
PostGIS, pgRouting, `readiness` e a revisão da API. Esse ensaio cobre a subida
dos contêineres; não valida HTTPS público, a malha aprovada ou a operação em VPS.

## Pré-requisitos

1. VPS Linux com Docker Engine e plugin Compose instalados conforme a
   [documentação oficial](https://docs.docker.com/engine/install/). Reserve
   espaço para o banco, backups e imagens; mantenha as portas 80 e 443 abertas.
2. Um domínio sob controle da equipe com registro A/AAAA apontando para a VPS.
   O Caddy usa esse nome e as portas 80/443 para obter e renovar o certificado.
3. Um commit aprovado do SPRain e um arquivo `.env.prod` **fora do Git**, com
   `SPRAIN_BUILD_COMMIT`, `SPRAIN_DOMAIN`, `ACME_EMAIL`, `DB_NAME`, `DB_USER`,
   `DB_PASSWORD`, `API_KEYS`, `TENANT_API_KEYS` e `WEBHOOK_SECRET_KEY`. Use
   `CORS_ORIGINS` somente para frontends servidos de outra origem; o painel
   entregue pela própria API não precisa dela.
4. Um banco inicial aprovado para o piloto, com esquema, PostGIS/pgRouting e
   malha conferida pela equipe responsável pelas rotas. O arquivo
   `db/ci/01_dump_nuclear.sql` contém também operações e veículos de ensaio;
   **não é uma carga automática adequada para transportadoras reais**. O
   `docker-compose.prod.yml` preserva o volume e não monta esse dump. A equipe
   precisa fornecer um procedimento de provisionamento sanitizado antes da
   primeira subida em uma VPS vazia.

## Configuração e subida

No checkout do commit aprovado, crie `.env.prod` com permissões restritas. Não
copie o `.env` do desenvolvimento. Confira a composição antes de subir:

```sh
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml config --quiet
```

Inicie **somente** o PostgreSQL na primeira instalação:

```sh
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml up -d --wait sprain_db
```

Pare nesse ponto até a equipe responsável pela malha fornecer e aplicar o
provisionamento sanitizado. A composição de produção não carrega os arquivos de
`db/ci` automaticamente; o dump de CI contém dados de ensaio. Antes de iniciar
a API, confira no **banco novo** as extensões e a malha aprovada:

```sh
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml exec -T sprain_db \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT PostGIS_Version(), pgr_version()"'
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml exec -T sprain_db \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM trechos_osm"'
```

As duas versões devem aparecer, a contagem de trechos deve ser positiva e a
equipe de rotas deve conferir a origem e a cobertura da malha. Só então inicie
a API e o proxy:

```sh
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml up -d --build --wait \
  sprain_api caddy

docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml ps

curl -fsS "https://SEU_DOMINIO/api/v1/health/readiness"
curl -I "https://SEU_DOMINIO/static/b2b.html"
```

Substitua `SEU_DOMINIO` pelo nome configurado; confira `READY`, PostGIS
operacional, certificado válido, redirecionamento HTTP para HTTPS e os
cabeçalhos `Strict-Transport-Security`, `X-Content-Type-Options` e
`Referrer-Policy`. Execute essas consultas também de **outra rede**, não só da
VPS. Se o frontend estiver em outra origem, teste o preflight CORS dessa origem
e permita somente seu endereço HTTPS em `CORS_ORIGINS`.

O Caddy é o único serviço com portas públicas. A API continua na porta de
loopback 8000 para diagnóstico local; PostgreSQL não publica porta no host.
Os volumes `sprain_db_prod_data`, `sprain_caddy_data` e `sprain_caddy_config`
devem sobreviver a atualizações. Nunca use `down -v` em ambiente com dados.

## Troca de versão e retorno da API

Após o primeiro deploy, faça atualizações com uma imagem já construída e
identificada por digest. `compose.release.yml` altera **somente** a imagem da
API; o banco, o proxy e seus volumes não entram no comando de troca. Antes de
alterar a API, registre o digest e o commit da imagem em execução, confira a
compatibilidade das migrações com a versão anterior e faça um backup validado.
O script abaixo recusa imagem sem o label de revisão correspondente:

```sh
export SPRAIN_API_IMAGE='sha256:DIGEST_DA_NOVA_IMAGEM'
export SPRAIN_BUILD_COMMIT='SHA_COMPLETO_DO_NOVO_COMMIT'
python3 scripts/validar_imagem_release.py \
  --image "$SPRAIN_API_IMAGE" --commit "$SPRAIN_BUILD_COMMIT"
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml -f compose.release.yml \
  config --quiet
docker compose --env-file .env.prod -p sprain-prod \
  -f docker-compose.prod.yml -f compose.vps.yml -f compose.release.yml \
  up -d --no-deps --no-build --wait sprain_api
curl -fsS "https://SEU_DOMINIO/api/v1/health/readiness"
```

Confira também `/api/v1/operacional/versao` com ADMIN e uma consulta de rota
autorizada. Se a API falhar e o esquema ainda for compatível com a imagem
anterior, repita a validação e o `up` acima com o **digest anterior** e o SHA
anterior em `SPRAIN_API_IMAGE` e `SPRAIN_BUILD_COMMIT`. Isso recria apenas o
contêiner da API. `--no-build` e `pull_policy: never` exigem que ambas as imagens
estejam carregadas previamente no host; não há download inesperado durante o
retorno. Nunca use `down -v`, `DROP DATABASE` ou downgrade SQL improvisado.
Um retorno de imagem não desfaz escritas feitas pela versão nova.

Esse procedimento ainda precisa de ensaio em uma VPS de homologação com banco
isolado, versões conhecidas e um fluxo de viagem antes e depois da troca. A
validação estática e o script de imagem não constituem prova de rollback real.

## Coleta meteorológica

O serviço `sprain_chuva` fica em perfil separado, com healthcheck próprio.
**Não o ative para o piloto comercial enquanto o provedor e a licença de uso
não estiverem aprovados.** O código atual usa o endpoint gratuito da Open-Meteo,
que é [restrito a uso não comercial](https://open-meteo.com/en/terms).
O agendador interno de clima do corredor também fica desligado em produção:
ele consulta a mesma API gratuita e uma fonte de redundância ainda sem aprovação
para o piloto. Dados antigos devem aparecer como ausentes ou desatualizados,
nunca como chuva atual. Para ativar a coleta, primeiro integre uma fonte
permitida para uso comercial e revise os dois caminhos de atualização.
Depois de configurar uma fonte permitida e conferir as estações ativas, inicie
o perfil com `--profile chuva` e verifique o estado do contêiner. A API também
possui esse agendador interno de telemetria, que exigirá revisão antes de
ser reativado em produção.

## Evidência necessária para concluir esta etapa

- URL HTTPS externa, certificado válido e preflight CORS verificados de fora.
- `readiness` com PostGIS ativo e contagem da malha aprovada, sem dados de ensaio.
- API e coletor com healthchecks saudáveis por um período de observação.
- Versão retornada por `/api/v1/operacional/versao` igual ao commit implantado.
- Backup externo, restauração, alertas e isolamento entre empresas validados nas
  etapas operacionais posteriores.
