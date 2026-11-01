#!/usr/bin/env python3
"""
FIRA Production Configuration Generator
Generates high-entropy cryptographic secrets and produces a secure .env.production file.
"""

import secrets
import base64
import os
from pathlib import Path

def generate_fernet_key() -> str:
    """Generate a valid 32-byte urlsafe base64-encoded Fernet key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8")

def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    prod_env_path = root_dir / ".env.production"

    if prod_env_path.exists():
        print(f"[!] Warning: {prod_env_path} already exists.")
        choice = input("Do you want to overwrite it with newly generated keys? (y/N): ").strip().lower()
        if choice != "y":
            print("Aborted. Existing configuration preserved.")
            return

    # Cryptographic secret generation
    pg_password = secrets.token_urlsafe(24)
    minio_password = secrets.token_urlsafe(24)
    jwt_secret = secrets.token_hex(32)  # 64 hex characters
    mfa_encryption_key = generate_fernet_key()

    content = f"""# ==============================================================================
# FIRA PRODUCTION ENVIRONMENT SECRETS
# Generated automatically on deployment setup. Keep this file strictly confidential!
# ==============================================================================

# Database Settings
POSTGRES_USER=fira_prod_user
POSTGRES_PASSWORD={pg_password}
POSTGRES_DB=fira_production_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=postgresql+psycopg://fira_prod_user:{pg_password}@postgres:5432/fira_production_db

# Redis Cache & Message Broker
REDIS_URL=redis://redis:6379/0

# Object Storage (MinIO / S3)
MINIO_ENDPOINT=http://minio:9000
MINIO_ROOT_USER=fira_storage_admin
MINIO_ROOT_PASSWORD={minio_password}
MINIO_BUCKET=fira-documents

# Cryptographic Keys (Mandatory Enterprise Security)
JWT_SECRET={jwt_secret}
MFA_ENCRYPTION_KEY={mfa_encryption_key}
SESSION_EXPIRE_MINUTES=60

# Compliance & Data Retention (Sec 57 VAT Act compliant default: 24 to 72 months)
DEFAULT_RETENTION_MONTHS=36
"""

    with open(prod_env_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[+] Successfully generated production environment configuration: {prod_env_path}")
    print("[+] Cryptographically unique keys generated for JWT, MFA Fernet encryption, and PostgreSQL.")

if __name__ == "__main__":
    main()
