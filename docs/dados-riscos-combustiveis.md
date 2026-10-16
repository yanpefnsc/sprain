# Dados de tombamentos, roubo de carga e combustiveis

Esta camada fornece dados historicos para a torre B2B. Ela nao libera passagem,
nao altera uma rota automaticamente e nao transforma ocorrencias passadas em
probabilidade individual de sinistro. O processo de importacao roda fora da API;
as consultas de rota leem apenas o PostGIS.

## Fontes e precisao

| Tema | Fonte | Informacao realmente disponivel |
| --- | --- | --- |
| Tombamentos | [ARTESP, acidentes em rodovias estaduais concedidas](https://dadosabertos.artesp.sp.gov.br/dataset/acidentes) | Data, classe, veiculos envolvidos, rodovia, km e coordenadas. O filtro identifica tombamento **com** caminhao/carreta/bitrem envolvido; nao prova qual deles tombou. Cobertura limitada a rodovias concedidas. |
| Precos | [ANP, pesquisa de precos por posto](https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/levantamento-de-precos-de-combustiveis-ultimas-semanas-pesquisadas) | CNPJ, endereco, produto, preco e data da coleta. A pesquisa nao representa todos os postos nem preco em tempo real. |
| Localizacao de postos | [ANP, API de Revendedores](https://www.gov.br/anp/pt-br/centrais-de-conteudo/paineis-dinamicos-da-anp/paineis-dinamicos-do-abastecimento/painel-dinamico-de-relatorio-de-revenda) | Cadastro de postos em operacao, com coordenadas quando disponiveis. A propria ANP marca as posicoes retornadas como **nao validadas**; a API SPRain as identifica como candidatas e nao as utiliza em decisoes de navegacao. |
| Roubo de carga | [SSP-SP, estatisticas trimestrais](https://www.ssp.sp.gov.br/estatistica/dados-trimestrais) | Contagens por Capital, Grande SP, 10 DEINTERs e Estado. As 12 regioes policiais nao se sobrepoem; os totais sao conferidos a cada carga. Nao ha localizacao por via nem denominador de viagens/cargas para calcular taxa de risco. |

Nao colocar snapshots desses dados no Git. A API exibe a URL da fonte e a data
observada; `GET /api/v1/dados-publicos/fontes` informa a ultima importacao.
Falha de download/importacao termina com codigo de erro, preservando o ultimo
conjunto valido. Monitore a saida e a idade de `ultimo_sucesso_em`.

## Preparar e validar

A migracao `db/ci/04_dados_riscos_combustiveis.sql` e aditiva e idempotente.
Ela e aplicada na inicializacao da API e no fluxo de CI. O importador aplica
a mesma migracao apenas quando `--aplicar` e usado.

```sh
# Padrao: baixa as fontes oficiais, valida e imprime contagens; nao grava.
python scripts/sincronizar_dados_publicos.py todas

# Um ano de acidentes ou uma fonte isolada.
python scripts/sincronizar_dados_publicos.py artesp --anos 2025
python scripts/sincronizar_dados_publicos.py anp
python scripts/sincronizar_dados_publicos.py anp-cadastro
python scripts/sincronizar_dados_publicos.py ssp-roubo
```

Para gravar, configure `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` e
`DB_NAME` do ambiente de desenvolvimento/piloto e acrescente `--aplicar`.
Dentro do conteiner API, as variaveis ja vem do Compose:

```sh
docker compose exec -T -w /app api python scripts/sincronizar_dados_publicos.py todas --aplicar
```

Para atualizar automaticamente uma vez por dia, ative o servico separado:

```sh
docker compose --profile dados up -d dados-publicos
```

No ambiente Windows local, use as credenciais de desenvolvimento configuradas
no Compose override; nao use credenciais de producao. O servico inicia com uma
sincronizacao, repete a cada 24 horas e isola falhas por fonte. Tambem pode ser
executado uma vez com `python scripts/worker_dados_publicos.py --once`.

O container `dados-publicos` registra o andamento de cada fonte e tem um
healthcheck. Confira com `docker compose --profile dados ps` e consulte os logs
com `docker compose --profile dados logs dados-publicos`. O estado fica
`unhealthy` se a rodada falhar, se uma fonte nao avancar em 15 minutos ou se
uma nova rodada nao comecar ate 15 minutos depois do intervalo configurado.
O healthcheck sinaliza o problema no Docker, mas nao envia notificacoes por si
so; conecte um monitor externo aos estados do Docker para receber alertas de
indisponibilidade do worker. `WEBHOOK_ALERTA_DADOS` continua a informar falhas
individuais de importacao, quando configurado.

O importador procura os anos recentes no catalogo da ARTESP, o CSV mensal mais
recente de diesel e gasolina na ANP, o cadastro georreferenciado da ANP e os
trimestres publicados pela SSP-SP.
Repeticoes nao duplicam ocorrencias ou
precos; correcoes do CSV ARTESP desativam a versao anterior sem apaga-la. A
carga de cada arquivo ocorre em uma transacao. Um arquivo ARTESP vazio ou com
queda superior a 50% na contagem e recusado para revisao manual. Execute primeiro sem
`--aplicar` apos qualquer mudanca no formato das fontes.

### Coordenadas verificadas dos postos

O cadastro ANP fornece pontos candidatos para o mapa com
`localizacao_confirmada=false`, fonte, data de obtencao e acuracia quando
publicada. Postos sem preco pesquisado aparecem com `preco_litro=null`.
Esses pontos nao sao usados pela consulta de proximidade da rota. Para
promover um posto a localizacao conferida, verifique-o e forneca um CSV UTF-8
com as colunas abaixo:

```csv
cnpj,latitude,longitude,fonte,verificado_em
01234567000189,-22.9001,-47.1001,https://www.openstreetmap.org/node/123,2026-10-12T12:00:00-03:00
```

O exemplo mostra **formato**, nao uma coordenada validada do corredor.
O CNPJ deve existir nos dados importados da ANP. A fonte deve ser um URL HTTPS,
e a data deve ter fuso horario. Um registro mais antigo nao substitui uma
localizacao ja verificada em data posterior.

```sh
python scripts/sincronizar_dados_publicos.py coordenadas-postos --arquivo postos-conferidos.csv
python scripts/sincronizar_dados_publicos.py coordenadas-postos --arquivo postos-conferidos.csv --aplicar
```

### Roubo de carga

Os trimestres oficiais da SSP sao importados automaticamente para os dois anos
mais recentes. A consulta `GET /roubo-carga/por-regiao` ordena as 12 regioes
policiais do trimestre mais recente por **contagem** de registros. Capital,
Grande SP e os dez DEINTERs formam uma particao; o total estadual e guardado
separadamente. Nao chame a contagem de "indice" ou "probabilidade". Um mapa de
trechos com alertas de roubo requer uma fonte geocodificada confiavel.

```sh
python scripts/sincronizar_dados_publicos.py ssp-roubo --anos-ssp 2025 2026 --aplicar
```

O importador tambem aceita um CSV **agregado oficial ja normalizado**, com uma linha por
area e periodo para outras fontes verificadas. Exemplo apenas de formato:

```csv
nivel_geografico,area,periodo_inicio,periodo_fim,ocorrencias
REGIAO,CAMPINAS,2025-01-01,2025-12-31,25
```

Valores e cobertura precisam vir de uma fonte verificavel; nao use o exemplo
como dado real. Niveis permitidos: `ESTADO`, `REGIAO`, `MUNICIPIO`. Registre o
link oficial em `--url-fonte`. Este caminho complementar nao cria aviso de
roubo por trecho.

```sh
python scripts/sincronizar_dados_publicos.py roubo-carga --arquivo roubo-oficial.csv \
  --url-fonte https://www.ssp.sp.gov.br/estatistica/spcarga
```

## Contrato para os colegas

Todos os endpoints exigem uma API key B2B com perfil `ADMIN`, `OPERATOR` ou
`VIEWER`. Sao consultas; importacao acontece somente pelo processo separado.

| Endpoint | Uso |
| --- | --- |
| `GET /api/v1/dados-publicos/fontes` | Procedencia e ultimo sucesso. |
| `GET /api/v1/dados-publicos/tombamentos?bbox=min_lon,min_lat,max_lon,max_lat` | Pontos historicos da ARTESP em GeoJSON. |
| `GET /api/v1/dados-publicos/tombamentos/por-rodovia` | Contagem por rodovia, sem inferir probabilidade. |
| `GET /api/v1/dados-publicos/postos?produto=DIESEL%20S10&municipio=CAMPINAS` | Postos cadastrados e ultimo preco coletado, quando houver. Coordenadas ANP sao candidatas e marcadas como nao confirmadas. Use `bbox` e observe `truncado` no mapa. |
| `GET /api/v1/dados-publicos/roubo-carga` | Agregados por area e periodo, quando houver fonte importada. |
| `GET /api/v1/dados-publicos/roubo-carga/por-regiao` | Ranking do trimestre SSP mais recente por contagem, sem inferir taxa de risco. |
| `POST /api/v1/dados-publicos/consultar-rota` | Pontos historicos proximos de uma `LineString` GeoJSON e postos com localizacao conferida. Nao inclui roubo agregado como ponto. |

Corpo da consulta por rota:

```json
{
  "rota": {"type": "LineString", "coordinates": [[-48.0, -22.0], [-47.0, -22.9]]},
  "raio_tombamento_m": 500,
  "raio_posto_m": 3000,
  "produto": "DIESEL S10"
}
```

O colega de rotas pode consumir a consulta sem alterar o calculo de passagem
fisica. O frontend deve exibir fonte, data da ocorrencia/coleta e o aviso de
cobertura antes de representar esses dados no mapa.
