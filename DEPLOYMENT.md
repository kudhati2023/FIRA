# FIRA ENTERPRISE PRODUCTION DEPLOYMENT GUIDE

This guide provides instructions for deploying FIRA to production environments, including Cloud Linux VPS (Ubuntu/Debian) and Enterprise On-Premise Windows/Linux servers.

---

## 1. SYSTEM ARCHITECTURE (PRODUCTION)

```
[ Internet / Enterprise LAN ]
            │ (HTTP: 80 / HTTPS: 443)
            ▼
┌──────────────────────────────────────────────┐
│  Hardened Nginx Reverse Proxy (SSL + Gzip)   │
└──────┬────────────────────────────────┬──────┘
       │                                │
       ▼                                ▼
┌───────────────────────┐    ┌───────────────────────┐
│ Frontend Static SPA   │    │ FastAPI Backend API   │
│ (Nginx Alpine :3000)  │    │ (Uvicorn 4-workers)   │
└───────────────────────┘    └──────┬────────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌──────────────┐             ┌──────────────┐             ┌──────────────┐
│ PostgreSQL 16│             │   Redis 7    │             │ MinIO S3     │
│ Database     │             │ Cache/Broker │             │ Storage      │
└──────────────┘             └──────────────┘             └──────────────┘
```

---

## 2. PREREQUISITES
* **Hardware**: 2 CPU cores, 4 GB RAM, 20 GB SSD storage minimum (8 GB RAM recommended for 50,000+ invoice batches).
* **Software**:
  * Docker Engine (v24.0+) & Docker Compose (v2.20+)
  * Python 3.11+ (for key generation utility)

---

## 3. FAST TURNKEY DEPLOYMENT

### Option A: Linux Server (Ubuntu 22.04 / 24.04 LTS)
```bash
# 1. Clone repository
git clone https://github.com/kudhati2023/FIRA.git
cd FIRA

# 2. Make scripts executable
chmod +x deploy-prod.sh

# 3. Launch the production stack
./deploy-prod.sh
```
The script will automatically:
1. Generate cryptographically strong keys into `.env.production`.
2. Build production-optimized container images.
3. Apply all Alembic database schema migrations.
4. Launch the services under Docker Compose.

---

### Option B: Windows Server (PowerShell)
```powershell
# 1. Clone repository
git clone https://github.com/kudhati2023/FIRA.git
cd FIRA

# 2. Launch production stack
.\deploy-prod.ps1
```

---

## 4. DOMAIN NAME & SSL / TLS CONFIGURATION

To configure custom SSL certificates (e.g. from Let's Encrypt or corporate CA):

1. **Obtain SSL Certificate**:
   ```bash
   sudo certbot certonly --standalone -d fira.yourcompany.com
   ```
2. **Mount Certificates in `docker-compose.prod.yml`**:
   Uncomment or map certificate paths into `/etc/nginx/certs`:
   ```yaml
   volumes:
     - /etc/letsencrypt/live/fira.yourcompany.com/fullchain.pem:/etc/nginx/certs/fullchain.pem:ro
     - /etc/letsencrypt/live/fira.yourcompany.com/privkey.pem:/etc/nginx/certs/privkey.pem:ro
   ```
3. **Restart Nginx**:
   ```bash
   docker compose -f docker-compose.prod.yml restart nginx
   ```

---

## 5. DATABASE BACKUP & RESTORE PROCEDURE

### Automated Daily Backup Script (`backup.sh`):
```bash
#!/usr/bin/env bash
BACKUP_DIR="/var/backups/fira"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Dump PostgreSQL Database
docker exec fira_prod_postgres pg_dump -U fira_prod_user fira_production_db | gzip > "$BACKUP_DIR/db_$TIMESTAMP.sql.gz"

# Retain last 30 days
find "$BACKUP_DIR" -type f -name "db_*.sql.gz" -mtime +30 -delete
echo "[+] Backup completed: db_$TIMESTAMP.sql.gz"
```

### Database Restore Command:
```bash
gunzip < db_20261005_120000.sql.gz | docker exec -i fira_prod_postgres psql -U fira_prod_user -d fira_production_db
```

---

## 6. HEALTH CHECK & MONITORING
* **API Health Check**: `http://<your-server>/healthz` (Returns `{"status": "ok"}`)
* **View Logs**:
  ```bash
  docker compose -f docker-compose.prod.yml logs -f api
  docker compose -f docker-compose.prod.yml logs -f nginx
  ```
