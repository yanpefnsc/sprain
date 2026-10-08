$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "SPRain B2B - Checklist Pre-Deploy de Infraestrutura" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "`n[1/4] Verificando status dos containers Docker..." -ForegroundColor Yellow
$apiStatus = docker inspect -f '{{.State.Running}}' sprain_api 2>$null
$dbStatus = docker inspect -f '{{.State.Running}}' sprain_db 2>$null

if ($apiStatus -ne "true" -or $dbStatus -ne "true") {
    Write-Host "ERRO: Containers sprain_api ou sprain_db nao estao em execucao." -ForegroundColor Red
    exit 1
}
Write-Host "OK: Containers sprain_api e sprain_db estao ativos." -ForegroundColor Green

Write-Host "`n[2/4] Testando sondas de Healthcheck..." -ForegroundColor Yellow
$healthResp = docker exec -i sprain_api python -c "import httpx; r = httpx.get('http://127.0.0.1:8000/api/v1/health/readiness'); print(r.status_code, r.json().get('postgis'))"
Write-Host "Resposta Healthcheck: $healthResp" -ForegroundColor Green

Write-Host "`n[3/4] Validando documentacao OpenAPI estatica..." -ForegroundColor Yellow
if (Test-Path "api/openapi.json") {
    Write-Host "OK: api/openapi.json presente no repositorio." -ForegroundColor Green
} else {
    Write-Host "ALERTA: api/openapi.json ausente no host." -ForegroundColor Red
}

Write-Host "`n[4/4] Executando suite completa de 20 testes automatizados..." -ForegroundColor Yellow
docker exec -i -w /app/api sprain_api pytest tests/ -v

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==================================================" -ForegroundColor Green
    Write-Host "CHECKLIST APROVADO: SISTEMA APTO PARA DEPLOY B2B" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
} else {
    Write-Host "`n==================================================" -ForegroundColor Red
    Write-Host "FALHA NO CHECKLIST: TESTES REPROVADOS" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Red
    exit 1
}
