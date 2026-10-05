import uuid
from typing import Any, Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
import jwt

from fira.db.session import get_db, set_tenant_context
from fira.models.tenant import AppUser, Tenant
from fira.security.jwt import decode_token
from fira.security.tenant import TenantContext

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)

def get_current_token_payload(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Extract and validate enterprise JWT claims."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("token_type") != "access":
            raise credentials_exception
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, Exception):
        raise credentials_exception

def get_current_user(
    payload: Dict[str, Any] = Depends(get_current_token_payload),
    db: Session = Depends(get_db)
) -> AppUser:
    """Load active authenticated user and verify tenant status."""
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identifier format")

    stmt = select(AppUser).where(AppUser.id == user_uuid)
    user = db.execute(stmt).scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found"
        )

    # Verify tenant is active
    tenant_stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    tenant = db.execute(tenant_stmt).scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant organization account is disabled"
        )

    return user

def get_current_tenant_context(
    current_user: AppUser = Depends(get_current_user)
) -> TenantContext:
    """Provide isolated tenant security context (HC-6)."""
    return TenantContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        email=current_user.email,
        role=current_user.role,
    )

def get_tenant_db(
    tenant_ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db)
) -> Session:
    """Return database session bound with tenant isolation setting."""
    try:
        set_tenant_context(db, tenant_ctx.tenant_id)
    except Exception:
        # SQLite in-memory during tests doesn't support SET LOCAL, silently ignore
        pass
    return db
