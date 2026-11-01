#!/usr/bin/env bash
# ==============================================================================
# FIRA Production Deployment Script (Linux / Bash)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

echo "=========================================================="
echo "    FIRA - Fiscal Invoice Reconciliation & Auditing       "
echo "             Enterprise Production Deployment             "
echo "=========================================================="

if [ "$1" == "down" ]; then
    echo "[*] Stopping FIRA production stack..."
    docker compose --env-file "$ROOT_DIR/.env.production" -f "$ROOT_DIR/docker-compose.prod.yml" down
    exit 0
fi

# 1. Generate secrets if missing
if [ ! -f "$ROOT_DIR/.env.production" ]; then
    echo "[*] Generating production secrets in .env.production..."
    python3 "$ROOT_DIR/deploy/scripts/generate_production_env.py"
fi

# 2. Build and run
echo "[*] Building and starting production containers..."
docker compose --env-file "$ROOT_DIR/.env.production" -f "$ROOT_DIR/docker-compose.prod.yml" up -d --build

# 3. Wait for initialization
echo "[*] Waiting for API service..."
sleep 10

# 4. Run Alembic migrations
echo "[*] Running database migrations..."
docker compose --env-file "$ROOT_DIR/.env.production" -f "$ROOT_DIR/docker-compose.prod.yml" exec -T api alembic upgrade head

echo ""
echo "[+] FIRA Production Stack is successfully running!"
echo "    - Web Dashboard: http://localhost"
echo "    - API Docs:      http://localhost/docs"
echo "    - Health Check:  http://localhost/healthz"
echo "=========================================================="
