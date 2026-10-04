# Plataforma de Mapeamento de Intransitabilidade Viaria por Enchentes

Pipeline geoespacial de alta resolucao para modelagem e classificacao do Indice de Vulnerabilidade de Intransitabilidade (IVI) em escala de trecho viario.

## Estrutura do Banco de Dados (PostGIS)
- `distrito_itaquera`: Poligono territorial de referencia.
- `trechos_osm`: 2.978 trechos viarios com atributos fisicos, hidrologicos e estatisticos.
- `hidrografia_osm`: Rede hidrografica detalhada extraida do OpenStreetMap.
- `setores_ibge_itaquera`: 315 setores censitarios oficiais do IBGE.
- `alagamentos_cge`: Ocorrencias historicas de pontos intransitaveis do CGE-SP.

## Metricas Consolidadas (Itaquera)
- **Critico (IVI >= 70):** 328 trechos viarios (Score medio: 79.8)
- **Alto (50 <= IVI < 70):** 1.052 trechos viarios (Score medio: 60.0)
- **Medio (30 <= IVI < 50):** 1.046 trechos viarios (Score medio: 41.4)
- **Baixo (IVI < 30):** 552 trechos viarios (Score medio: 22.3)

## Arquivos Gerados
- GeoPackage para GIS / Mapas Web: `dados/processados/vulnerabilidade_itaquera.gpkg`
