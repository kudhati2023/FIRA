from typing import List
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRETS = {
    "super_secret_jwt_signing_key_change_me_in_production_12345",
    "super_secret_mfa_encryption_key_change_me_32bytes_!!",
    "fira_password_secure_123",
    "minio_password_secure_123",
}

# HC-7: Mandatory scope-limitation disclaimer on all reports and outputs
MANDATORY_SCOPE_DISCLAIMER = (
    "This report is a reconciliation of the records supplied by the client against invoice "
    "data exported by the client from ZIMRA systems, as at the stated date. It is not tax "
    "advice, a tax opinion, or a substitute for professional judgement, and it does not "
    "constitute a VAT return or any representation to the Zimbabwe Revenue Authority. Findings "
    "reflect data status at the date of review and may change. The client remains responsible "
    "for the accuracy and completeness of records supplied and for all filings. Where a finding "
    "requires a technical VAT determination, refer it to a registered tax practitioner."
)

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = Field(default="development")  # development, staging, production, testing
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://fira_user:fira_password_secure_123@postgres:5432/fira_db"
    )
    
    # Redis
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    
    # Storage
    MINIO_ENDPOINT: str = Field(default="http://minio:9000")
    MINIO_ROOT_USER: str = Field(default="minio_admin")
    MINIO_ROOT_PASSWORD: str = Field(default="minio_password_secure_123")
    MINIO_BUCKET: str = Field(default="fira-documents")
    
    # Security - Cryptography & Tokens
    JWT_SECRET: str = Field(default="super_secret_jwt_signing_key_change_me_in_production_12345")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Standard enterprise session: 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7     # 7 days with rotation
    MFA_ENCRYPTION_KEY: str = Field(default="super_secret_mfa_encryption_key_change_me_32bytes_!!")
    
    # Security - CORS & Origins
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    
    # Security - Rate Limiting
    ENABLE_RATE_LIMITER: bool = True
    AUTH_RATE_LIMIT_PER_MINUTE: int = 5    # Strict brute-force protection
    API_RATE_LIMIT_PER_MINUTE: int = 100   # General API rate limit
    
    # Security - Account Lockout
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    
    # Security - Upload Limits
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    
    # Defaults
    DEFAULT_RETENTION_MONTHS: int = 24
    TIMEZONE: str = "Africa/Harare"

    # Mandatory Legal Notice (HC-7)
    DISCLAIMER_NOTICE: str = MANDATORY_SCOPE_DISCLAIMER

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET in INSECURE_DEFAULT_SECRETS or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "Production requires a strong JWT_SECRET with at least 32 characters and non-default value"
                )
            if self.MFA_ENCRYPTION_KEY in INSECURE_DEFAULT_SECRETS or len(self.MFA_ENCRYPTION_KEY) < 32:
                raise ValueError(
                    "Production requires a strong MFA_ENCRYPTION_KEY with at least 32 characters and non-default value"
                )
            if "*" in self.ALLOWED_ORIGINS:
                raise ValueError(
                    "Wildcard CORS origins are forbidden in production under enterprise standards"
                )
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
