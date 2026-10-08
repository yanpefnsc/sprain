# SPRain B2B - Release Notes v1.1.0

## Sumário Executivo
A versão v1.1.0 eleva o SPRain de uma plataforma de monitoramento de intransitabilidade para um **Motor de Otimização Logística Preditiva e Decisão Econômica em Tempo Real**. O sistema agora calcula a decisão operacional mais vantajosa financeiramente, ponderando custo de combustível, multas contratuais por atraso, custo/hora de equipe e preservação de carga.

## Novos Recursos
- **Decisão Econômica Preditiva (`POST /api/v1/logistica/decisao-economica`):** Trade-off comparativo entre rota física direta e rota alternativa resiliente.
- **Central de Frota em Tempo Real (`GET /api/v1/logistica/central-frota`):** Visão holística da frota ativa, classificação de risco por veículo e cálculo de prejuízos evitáveis.
- **Alertas Meteorológicos Severos (`GET /api/v1/logistica/alertas-meteorologicos`):** Classificação probabilística de interrupção viária por volume pluviométrico e vento.

## Métricas de Homologação
- Suite de Testes: 23 de 23 aprovados (100% de sucesso).
- Tag Oficial: v1.1.0.