# Backup e restauração de PostgreSQL/PostGIS

O script `scripts/postgres_backup.py` usa `pg_dump` e `pg_restore` dentro de um
contêiner PostgreSQL existente. Ele grava o arquivo em formato customizado e um
manifesto com tamanho e SHA-256. Não requer porta do banco exposta nem coloca
senha na linha de comando. Requer Python 3.9+ e Docker funcionando.

Antes de usá-lo, confirme o nome do contêiner, do banco e do usuário com quem
administra **esse ambiente**. Os exemplos abaixo são para um ambiente de teste;
substitua os valores pelos seus. Escolha uma pasta fora do repositório para os
backups e mantenha cópias em armazenamento seguro separado do computador.

```powershell
python scripts/postgres_backup.py backup `
  --container sprain_audit_20261014_db `
  --database enchentes `
  --user enchentes `
  --output-dir "$HOME\sprain-backups"
```

O comando imprime o caminho do arquivo `.dump` e do manifesto `.dump.json`.
Se ocorrer falha durante a criação, um arquivo `.partial` pode permanecer na
pasta; ele **não** é um backup válido. O script nunca sobrescreve um arquivo
existente.

Para uma checagem automatizável da cópia completa mais recente, use:

```powershell
python scripts/postgres_backup.py verify-latest `
  --database enchentes `
  --output-dir "$HOME\sprain-backups" `
  --max-age-hours 36
```

O comando retorna código 0 se o manifesto, o tamanho, o SHA-256 e a idade
estiverem corretos; retorna 1 caso contrário. Ele não acessa Docker nem o banco,
não modifica arquivos e não considera um `.partial` como backup. Configure seu
monitor para alertar quando o código for 1. Essa checagem não substitui o teste
de restauração: um hash válido só confirma que o arquivo ainda corresponde ao
manifesto criado no backup.

## Testar a restauração

Restaure sempre primeiro em **um banco novo**, de nome distinto. O script
confere o manifesto, a integridade do arquivo e se o banco de destino já
existe. Se existir, ele para sem alterá-lo. Se a restauração falhar, o banco
novo permanece para diagnóstico; ele nunca executa `DROP DATABASE`.

```powershell
python scripts/postgres_backup.py restore `
  --container sprain_audit_20261014_db `
  --new-database sprain_restore_test `
  --user enchentes `
  --backup "$HOME\sprain-backups\sprain-enchentes-ARQUIVO.dump"
```

Depois compare tabelas e extensões entre origem e cópia, por exemplo:

```powershell
docker exec sprain_audit_20261014_db psql -U enchentes -d sprain_restore_test -c "SELECT PostGIS_Version();"
docker exec sprain_audit_20261014_db psql -U enchentes -d sprain_restore_test -c "SELECT count(*) FROM trechos_osm;"
```

O backup inclui a estrutura e os dados do banco especificado. Ele não inclui
arquivos `.env`, imagens Docker, segredos, nem outros bancos/volumes. Para uma
rotina de produção, use também a cópia criptografada e o teste de restauração
abaixo. Não considere um backup operacional até verificar uma restauração com
dados reais do ambiente e uma cópia armazenada fora do servidor.

## Cópia criptografada para armazenamento externo

`scripts/backup_offsite.py` cria um backup em pasta exclusiva, confere o SHA-256,
envia os arquivos para um destino `rclone crypt` com `--immutable` e executa
`rclone cryptcheck`. Não apaga arquivos locais ou remotos. Exige Python 3.9+,
Docker e rclone. Configure o rclone **fora do repositório** com um remote de
armazenamento externo (por exemplo, S3 compatível) e um remote `crypt` sobre
ele. O remote `crypt` precisa ter senha própria e `remote` apontando para o
armazenamento externo. Proteja `/etc/sprain/rclone.conf` com permissão 0600;
ela contém os meios de decifrar o backup. Guarde uma cópia segura da configuração
e da senha fora do servidor. A configuração abaixo é um **formato ilustrativo**,
não contém credenciais:

```ini
[armazenamento]
type = s3
provider = Other
endpoint = ENDPOINT_DO_PROVEDOR
access_key_id = CONFIGURAR_FORA_DO_GIT
secret_access_key = CONFIGURAR_FORA_DO_GIT

[spraincrypt]
type = crypt
remote = armazenamento:BUCKET/sprain
password = GERAR_COM_RCLONE_CONFIG
filename_encryption = standard
directory_name_encryption = true
```

Após configurar as credenciais reais no servidor, faça uma execução manual:

```bash
python3 scripts/backup_offsite.py run \
  --container sprain_db_prod --database "$DB_NAME" --user "$DB_USER" \
  --staging-dir /var/lib/sprain-backup/staging \
  --remote spraincrypt: --config /etc/sprain/rclone.conf
```

O serviço e timer em `deploy/systemd/sprain-backup.*` agendam essa execução
diariamente às 03:15 no fuso do servidor. Crie `/etc/sprain/backup.env`, fora
do Git, com `SPRAIN_DB_CONTAINER=sprain_db_prod`, `SPRAIN_DB_NAME`,
`SPRAIN_DB_USER` e `SPRAIN_BACKUP_REMOTE=spraincrypt:`. Ajuste os valores ao
ambiente. Instale os dois arquivos em `/etc/systemd/system/`, rode
`systemctl daemon-reload` e habilite `sprain-backup.timer` **somente após** a
execução manual e o teste de restauração. O serviço acessa o socket Docker e
deve rodar em um servidor administrado pela equipe.

Para testar a cópia externa, use o identificador impresso na execução e baixe
para uma pasta nova. O download decifra o arquivo e valida o SHA-256:

```bash
python3 scripts/backup_offsite.py fetch \
  --database "$DB_NAME" --run-id IDENTIFICADOR_DA_EXECUCAO \
  --download-dir /var/lib/sprain-backup/restore-test \
  --remote spraincrypt: --config /etc/sprain/rclone.conf
```

Em seguida, restaure o `.dump` baixado **somente em um banco novo**, usando o
comando `restore` acima, e compare PostGIS, trechos e viagens com a origem.
Repita esse ensaio periodicamente; o timer de cópia não prova recuperação.

Defina uma retenção inicial de 14 dias no armazenamento externo apenas depois
de confirmar a política com a equipe e verificar ao menos uma restauração. Não
há exclusão automática no script. A pasta local também não é limpa por ele;
dimensione espaço e programe uma política de limpeza aprovada. Sem um destino
externo configurado, alertas de falha e uma restauração real desse destino,
esta rotina está preparada, mas **não está operacional em produção**.

O CI executa `backup`, `verify-latest` e `restore` após os testes de API, em um
banco novo chamado `sprain_restore_ci` no PostgreSQL descartável do runner.
Compara a contagem de `trechos_osm` entre origem e cópia e consulta a extensão
PostGIS restaurada. Esse ensaio verifica o caminho básico a cada PR; não valida
retenção, cópia externa ou restauração do banco de produção.

`scripts/check_deploy.ps1` faz apenas verificações básicas de Compose e
readiness. Ele não roda testes contra um banco em uso nem afirma que uma
implantação está pronta para produção.
