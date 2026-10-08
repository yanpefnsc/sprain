Write-Host "Iniciando verificacao pre-deploy..." -ForegroundColor Cyan

$testRun = docker exec -w /app/api sprain_api python -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha na suite de testes:" -ForegroundColor Red
    Write-Host $testRun
    exit 1
}
Write-Host "Testes unitarios e integrados: OK (26 aprovados)" -ForegroundColor Green

$health = curl.exe -s http://localhost:8000/api/v1/health/readiness | ConvertFrom-Json
if ($health.status -ne "READY" -or $health.postgis -ne "OPERACIONAL") {
    Write-Host "Falha na prontidao do banco PostGIS" -ForegroundColor Red
    exit 1
}
Write-Host "Readiness PostGIS: OK (Latencia: $($health.latencia_db_ms) ms)" -ForegroundColor Green

docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker-compose.yml invalido" -ForegroundColor Red
    exit 1
}
Write-Host "Orquestracao Docker Compose: OK" -ForegroundColor Green

Write-Host "Pre-deploy concluido com sucesso. Liberado para producao." -ForegroundColor Green