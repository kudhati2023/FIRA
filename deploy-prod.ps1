<#
.SYNOPSIS
    FIRA Production Deployment Script (PowerShell)
.DESCRIPTION
    Automates deployment of the complete FIRA stack for production use.
#>

param(
    [switch]$BuildOnly,
    [switch]$MigrateOnly,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot

if ($Down) {
    Write-Host "[*] Stopping FIRA production stack..." -ForegroundColor Yellow
    docker compose --env-file "$RootDir\.env.production" -f "$RootDir\docker-compose.prod.yml" down
    exit 0
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    FIRA - Fiscal Invoice Reconciliation & Auditing       " -ForegroundColor Cyan
Write-Host "             Enterprise Production Deployment             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check or generate production environment secrets
if (-not (Test-Path "$RootDir\.env.production")) {
    Write-Host "[*] Generating production secrets in .env.production..." -ForegroundColor Yellow
    py -3.11 "$RootDir\deploy\scripts\generate_production_env.py"
}

if ($MigrateOnly) {
    Write-Host "[*] Running database migrations..." -ForegroundColor Cyan
    docker compose --env-file "$RootDir\.env.production" -f "$RootDir\docker-compose.prod.yml" exec api alembic upgrade head
    exit 0
}

# 2. Build and launch containers
Write-Host "[*] Building and starting production containers..." -ForegroundColor Cyan
docker compose --env-file "$RootDir\.env.production" -f "$RootDir\docker-compose.prod.yml" up -d --build

# 3. Wait for database and api
Write-Host "[*] Waiting for API container to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 8

# 4. Run Alembic migrations
Write-Host "[*] Executing database schema migrations..." -ForegroundColor Cyan
docker compose --env-file "$RootDir\.env.production" -f "$RootDir\docker-compose.prod.yml" exec api alembic upgrade head

Write-Host "`n[+] FIRA Production Stack is LIVE!" -ForegroundColor Green
Write-Host "    - Web Dashboard:   http://localhost (or configured server IP/domain)" -ForegroundColor White
Write-Host "    - API Docs:        http://localhost/docs" -ForegroundColor White
Write-Host "    - Health Check:    http://localhost/healthz" -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
