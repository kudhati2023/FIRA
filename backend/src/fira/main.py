from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fira.api.auth import router as auth_router
from fira.api.clients import router as clients_router
from fira.api.engagements import router as engagements_router
from fira.api.documents import router as documents_router
from fira.api.exceptions import register_exception_handlers
from fira.config import MANDATORY_SCOPE_DISCLAIMER, settings
from fira.security.headers import SecurityHeadersMiddleware
from fira.security.rate_limiter import RateLimitMiddleware
from fira.security.request_id import RequestIDMiddleware

app = FastAPI(
    title="FIRA — FDMS Input Tax Recovery Platform API",
    description="Zimbabwean VAT reconciliation and exception-management system",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# 1. Register Request ID Tracing Middleware (outermost for all responses)
app.add_middleware(RequestIDMiddleware)

# 2. Register Enterprise HTTP Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 3. Register Rate Limiting Middleware
app.add_middleware(RateLimitMiddleware)

# 4. Strict CORS Configuration (OWASP ASVS compliant)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

# 5. Register Sanitized Exception Handlers (OWASP A05)
register_exception_handlers(app)

# 6. Register Routers
app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(engagements_router)
app.include_router(documents_router)

@app.get("/healthz", status_code=200)
@app.get("/api/healthz", status_code=200)
def health_check() -> dict[str, str]:
    """Liveness check with mandatory regulatory scope disclaimer (HC-7)."""
    return {
        "status": "ok",
        "notice": MANDATORY_SCOPE_DISCLAIMER,
    }

@app.get("/readyz", status_code=200)
@app.get("/api/readyz", status_code=200)
def readiness_check() -> dict[str, str]:
    """Readiness check. In later milestones, this will check DB and Redis connectivity."""
    return {
        "status": "ready",
        "notice": MANDATORY_SCOPE_DISCLAIMER,
    }

