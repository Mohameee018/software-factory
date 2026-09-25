$ErrorActionPreference = 'Stop'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }
Write-Host 'Validating Compose configuration...'
docker compose config | Out-Null
Write-Host 'Building production images...'
docker compose build
Write-Host 'Starting bot and language workers...'
docker compose up -d
Write-Host 'Service status:'
docker compose ps
Write-Host 'Health snapshot:'
docker compose exec -T bot factory health
