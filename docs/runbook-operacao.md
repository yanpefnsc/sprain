# Runbook: deploy, rollback, backup e incidentes

Responsável de backend/infraestrutura para revisão: **yanpefnsc**.
Este documento é uma proposta executável para revisão conjunta. A existência
do PR ou a indicação do revisor não representam aprovação humana recebida.
Os ensaios isolados estão em [evidências](evidencias-validacao-3-6.md).
Para preparar um ambiente separado com validacoes equivalentes as de producao,
veja [homologacao isolada](homologacao-isolada.md).

## Identificar o ambiente antes de agir

Registrar responsável, data UTC, commit, imagem por digest, projeto Compose,
banco e volume. Confirmar porta/empresa e janela de manutenção. Não usar a base
de produção para pytest, demonstração, seed de teste ou importação experimental.
O Compose padrão pressupõe infraestrutura provisionada; o Compose demo/e2e não
é receita de produção.

Produção exige ENVIRONMENT=production, demo desativada, credenciais próprias,
TLS/ingress, CORS autorizado, segredo de assinatura, banco provisionado,
monitoramento e backup fora do host. A validação de configuração pode impedir
o startup com credenciais de exemplo. Nunca contornar essa validação.

Para checar disponibilidade pública de fora do servidor e avisar a equipe por
Discord, consulte [monitoramento-externo.md](monitoramento-externo.md).

## Deploy

Para anunciar uma janela planejada, defina `MANUTENCAO_INICIO`,
`MANUTENCAO_FIM` (ISO 8601 com fuso) e `MANUTENCAO_AVISO` (até 240 caracteres)
no ambiente da API e aplique a configuração aprovada. O endpoint público
`/api/v1/health/manutencao` e a página `/static/status.html` mostram o aviso
antes e durante a janela. Após o fim, o aviso desaparece automaticamente.
Configuração incompleta ou datas inválidas impedem a inicialização. O aviso não
bloqueia requisições e não muda readiness; mantenha o procedimento de deploy e
os healthchecks normais. Como a página está na mesma API, use monitor externo
para informar indisponibilidade total.

1. Executar CI e revisar diff e dependências. Registrar imagem anterior e nova;
   manter ambas disponíveis por digest. Aprovar mudanças de esquema e verificar
   compatibilidade reversa. A inicialização aplica schemas idempotentes; ainda
   assim revisar as alterações de banco antes de subir versão nova.
2. Fazer backup consistente, verificar hash e testar restore em banco novo.
   Guardar dump e manifesto em armazenamento privado fora do host; definir com
   infraestrutura retenção, RPO/RTO e criptografia. Não publicar dumps.
3. Construir/testar imagem do commit aprovado. Em homologação isolada:
   `docker compose -f compose.demo.yml up -d --build --wait`.
   Em produção usar a imagem imutável e configuração aprovadas para o ambiente;
   não copiar senhas/volumes da demonstração. Se usar o build do
   `docker-compose.prod.yml`, definir `SPRAIN_BUILD_COMMIT` com os 40 caracteres
   do commit aprovado antes de gerar a configuração ou a imagem; o Compose
   recusa o build sem essa variável. O identificador não prova que a árvore de
   trabalho está limpa nem substitui a conferência do digest da imagem.
4. Aplicar rollout por serviço após backup e plano de rollback. Executar
   readiness/liveness, login individual, leitura da empresa, consulta de rota,
   decisão de ensaio autorizada e relatório. Conferir dados de outra empresa
   inacessíveis, geometrias e fontes antigas/indisponíveis. Consultar
   `GET /api/v1/operacional/versao` com sessão ADMIN e comparar a revisão de
   40 caracteres com o commit da imagem aprovada. Uma revisão ausente indica
   build sem `SPRAIN_BUILD_COMMIT`; não afirmar qual código está em execução.
5. Monitorar erros, latência, importações e idade das fontes. Registrar resultado
   e critérios de reversão. Nunca remover volume para corrigir startup.

Para observar tamanho e conexões do PostgreSQL, execute no host de operação,
com as variáveis DB_* do ambiente correto, `python scripts/monitorar_banco.py`.
O comando faz apenas uma consulta em sessão de leitura e emite JSON. Guarde a
série temporal em observabilidade de acesso restrito; uma amostra isolada não
define tendência nem substitui alertas. `tamanho_banco_bytes` abrange todo o
banco conectado, não uma empresa. `conexoes_banco` conta conexões nesse banco;
`conexoes_servidor` e `limite_global_conexoes` abrangem a instância PostgreSQL.
A porcentagem é indicativa: conexões reservadas, outros bancos e limites do pool
reduzem a capacidade efetivamente disponível. O comando não mede espaço livre
em disco, não prevê crescimento e não estabelece um limite de alerta.

## Rollback

1. Conter a falha e preservar logs/estado. Se houver suspeita de corrupção,
   impedir novas escritas pelo mecanismo operacional aprovado, sem destruir dados.
2. Conferir compatibilidade da imagem anterior com o esquema atual. Para falha
   só de aplicação, voltar ao digest anterior, mantendo o banco e volume.
3. Repetir readiness e fluxos críticos, comparar contagens e observar erros.
   Registrar o digest e a revisão devolvida por `/api/v1/operacional/versao`.
   Reverter imagem não desfaz
   alterações já gravadas.
4. Se esquema/dados forem incompatíveis, restaurar backup em banco **novo**,
   validar e planejar troca de conexão com infraestrutura. Definir como
   reconciliar escritas posteriores ao backup. Não sobrescrever o original nem
   executar downgrade SQL improvisado.

## Backup e restauração de ensaio

Exemplo exclusivo do banco sintético e2e, com Docker no PATH:

```sh
python scripts/postgres_backup.py backup --container sprain-e2e-db-1 --database sprain_demo_e2e --user sprain_test --output-dir ../backups-privados
python scripts/postgres_backup.py verify-latest --database sprain_demo_e2e --output-dir ../backups-privados --max-age-hours 24
python scripts/postgres_backup.py restore --container sprain-e2e-db-1 --user sprain_test --new-database sprain_restore_ensaio --backup ../backups-privados/ARQUIVO.dump
```

Substituir ARQUIVO pelo nome gerado. O restore recusa banco existente e confere
o manifesto SHA-256 antes de restaurar. Comparar tabelas, contagens, extensões
PostGIS/pgRouting e consultas representativas; conferir usuários/tenant sem
expor senhas. Subir uma API isolada contra a cópia e testar readiness antes de
considerar uma troca. Guardar duração e resultado, não só a mensagem do comando.
Ver [guia detalhado](backup-restauracao-postgis.md).

## Incidentes

| Sintoma | Verificação e contenção | Recuperação e aceite |
| --- | --- | --- |
| API indisponível | Readiness, logs, imagem e banco; preservar evidência | Corrigir configuração ou voltar imagem compatível; testar login e consulta |
| Falha/atraso de fonte | Painel interno: fonte, último sucesso, erro e cobertura | Reprocessar importador aprovado; conferir data/quantidade; não declarar risco zero |
| Geometria ou custo incoerente | Fonte, unidade, caminhão, praça/eixos, premissas e selo | Conter recomendação afetada, corrigir entrada/importação e repetir cálculo |
| Credencial comprometida | Revogar sessão/conta/chave afetada, preservar auditoria | Rotacionar pelo mecanismo aprovado, verificar isolamento e acessos recentes |
| Dado corrompido | Parar escritas afetadas e preservar banco original | Restaurar em banco novo, validar e reconciliar antes de trocar |
| Webhook falhando | Destino, DNS público, TLS e tentativas; sem segredos nos logs | Corrigir destino/configuração; não desativar verificação SSRF/TLS |

Registrar início, escopo/empresas, commit, responsável, ações, evidências e
encerramento. Logs devem ter acesso restrito; remover credenciais de qualquer
relatório compartilhado. O envio de webhooks usa IP público validado, sem
redirecionamento/proxy de ambiente e com TLS no nome original. Gateway de saída
deve preservar essas garantias.

## Revisão conjunta a registrar

- [ ] yanpefnsc revisou deploy/rollback e compatibilidade de esquema.
- [ ] Equipe definiu RPO/RTO, retenção, destino de backup e responsáveis.
- [ ] Restore e rollback foram repetidos no ambiente de homologação da equipe.
- [ ] Houve aceite do ambiente produtivo e dos alertas operacionais.

Ensaios locais comprovam o procedimento naquele ambiente; não substituem esses
aceites nem constituem deploy produtivo realizado.
