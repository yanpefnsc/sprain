# SPRain B2B - Guia de Operacao e Deploy Corporativo

## 1. Visao Geral da Arquitetura
O SPRain opera em topologia conteinerizada de microsservicos:
- sprain_api: API FastAPI assincrona, observabilidade via middleware, governanca multitenant, RBAC, cache TTL e webhooks HMAC-SHA256.
- sprain_db: PostGIS 15 / pgRouting sobre malha viaria vetorial.

## 2. Pre-Requisitos
- Docker Engine 24+ e Docker Compose v2+
- Portas: 8000 (API) e 5432 (PostGIS, opcional no host)
- 4 vCPUs e 8 GB de RAM recomendados.

## 3. Checklist Pre-Deploy Automatizado
Antes de cada release:
`powershell
.\scripts\check_deploy.ps1
`

## 4. Inicializacao em Producao
`ash
cp .env.example .env
docker compose -f docker-compose.prod.yml up -d --build
`

## 5. Endpoints de Verificacao
- Liveness: GET /api/v1/health/liveness
- Readiness: GET /api/v1/health/readiness
- Swagger UI: GET /docs
- OpenAPI JSON: GET /openapi.json
- Metricas: GET /api/v1/logistica/metricas
