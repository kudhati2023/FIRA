import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fira.config import settings
from fira.db.session import get_db
from fira.models.tenant import AppUser, Tenant, UserRole
from fira.security.audit import log_audit_event
from fira.security.crypto import (
    decrypt_secret,
    encrypt_secret,
    generate_backup_codes,
    generate_totp_secret,
    get_totp_uri,
    hash_password,
    verify_password,
    verify_totp_code,
)
from fira.security.dependencies import (
    get_current_token_payload,
    get_current_user,
)
from fira.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
)
from fira.security.password_policy import validate_password_complexity

router = APIRouter(prefix="/api/v1/auth", tags=["Enterprise Authentication"])

# Failed attempt tracker for Account Lockout
_failed_attempts: Dict[str, List[float]] = defaultdict(list)
# In-flight MFA setup secrets pending verification: user_id -> plain_secret
_pending_mfa_secrets: Dict[uuid.UUID, str] = {}

def _check_account_lockout(email: str) -> None:
    now = time.time()
    cutoff = now - (settings.LOCKOUT_DURATION_MINUTES * 60)
    attempts = [t for t in _failed_attempts[email] if t > cutoff]
    _failed_attempts[email] = attempts

    if len(attempts) >= settings.MAX_LOGIN_ATTEMPTS:
        remaining_sec = int(attempts[0] + (settings.LOCKOUT_DURATION_MINUTES * 60) - now)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account temporarily locked due to excessive failed attempts. Try again in {max(1, remaining_sec // 60)} minutes.",
        )

def _record_failed_attempt(email: str) -> None:
    _failed_attempts[email].append(time.time())

def _reset_failed_attempts(email: str) -> None:
    _failed_attempts.pop(email, None)


# --- Request/Response Schemas ---

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    password: str
    mfa_code: Optional[str] = Field(default=None, description="6-digit TOTP code if MFA is enabled")

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class RefreshRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class MFASetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    instructions: str

class MFAVerifyRequest(BaseModel):
    code: str

class MFAVerifyResponse(BaseModel):
    status: str
    backup_codes: List[str]

class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: uuid.UUID
    tenant_name: str
    mfa_enabled: bool


# --- Auth Endpoints ---

@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Enterprise login endpoint with Argon2id verification, account lockout,
    MFA enforcement, and tamper-evident audit logging.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    clean_email = payload.email.strip().lower()

    # 1. Check account lockout
    _check_account_lockout(clean_email)

    # 2. Look up user
    stmt = select(AppUser).where(AppUser.email == clean_email)
    user = db.execute(stmt).scalar_one_or_none()

    if not user or not verify_password(user.password_hash, payload.password):
        _record_failed_attempt(clean_email)
        # Log failed login attempt
        tenant_id = user.tenant_id if user else uuid.UUID(int=0)
        log_audit_event(
            db=db,
            tenant_id=tenant_id,
            actor_user_id=user.id if user else None,
            action="AUTH_LOGIN_FAILED",
            entity_type="app_user",
            entity_id=clean_email,
            ip_address=client_ip,
            user_agent=user_agent,
            after_json={"reason": "Invalid credentials"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been deactivated. Contact your administrator.",
        )

    # 3. Check MFA if enabled
    if user.mfa_secret_encrypted:
        if not payload.mfa_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required for this account.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        plain_secret = decrypt_secret(user.mfa_secret_encrypted)
        if not verify_totp_code(plain_secret, payload.mfa_code):
            _record_failed_attempt(clean_email)
            log_audit_event(
                db=db,
                tenant_id=user.tenant_id,
                actor_user_id=user.id,
                action="AUTH_MFA_FAILED",
                entity_type="app_user",
                entity_id=str(user.id),
                ip_address=client_ip,
                user_agent=user_agent,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired MFA authentication code.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 4. Successful login
    _reset_failed_attempts(clean_email)
    user.last_login_at = datetime.now(timezone.utc)

    # Issue tokens
    access_token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        role=user.role.value,
    )
    refresh_token = create_refresh_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
    )

    # Audit success
    log_audit_event(
        db=db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="AUTH_LOGIN_SUCCESS",
        entity_type="app_user",
        entity_id=str(user.id),
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "tenant_id": str(user.tenant_id),
            "tenant_name": user.tenant.name if user.tenant else "Default Practice",
        },
    )

@router.post("/refresh", response_model=TokenResponse)
def refresh_token_endpoint(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Rotate enterprise refresh token and issue fresh access token."""
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("token_type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

        user_id = uuid.UUID(decoded["sub"])
        user = db.execute(select(AppUser).where(AppUser.id == user_id)).scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

        # Revoke old refresh token (token rotation)
        old_jti = decoded.get("jti")
        if old_jti:
            revoke_token(old_jti, ttl_seconds=86400 * settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # Issue new token pair
        new_access = create_access_token(
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            email=user.email,
            role=user.role.value,
        )
        new_refresh = create_refresh_token(
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
        )

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "tenant_id": str(user.tenant_id),
                "tenant_name": user.tenant.name if user.tenant else "Default Practice",
            },
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    request: Request,
    current_user: AppUser = Depends(get_current_user),
    token_payload: Dict[str, Any] = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Revoke active JWT token and record audit trail."""
    jti = token_payload.get("jti")
    if jti:
        revoke_token(jti, ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="AUTH_LOGOUT",
        entity_type="app_user",
        entity_id=str(current_user.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return {"status": "logged_out", "message": "Token successfully revoked."}

@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileResponse:
    """Return authenticated caller's profile and active tenant."""
    tenant = db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id)).scalar_one()
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role.value,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        mfa_enabled=bool(current_user.mfa_secret_encrypted),
    )

@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: AppUser = Depends(get_current_user),
    token_payload: Dict[str, Any] = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Verify current password, validate NIST SP 800-63B rules, and update hash."""
    if not verify_password(current_user.password_hash, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed.",
        )

    # Validate complexity
    is_valid, errors = validate_password_complexity(payload.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"New password does not meet security standards: {'; '.join(errors)}",
        )

    # Update hash
    current_user.password_hash = hash_password(payload.new_password)

    # Invalidate current token to require re-authentication
    jti = token_payload.get("jti")
    if jti:
        revoke_token(jti, ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="AUTH_PASSWORD_CHANGED",
        entity_type="app_user",
        entity_id=str(current_user.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return {"status": "success", "message": "Password updated successfully. Please log in again."}

@router.post("/mfa/setup", response_model=MFASetupResponse)
def setup_mfa(
    current_user: AppUser = Depends(get_current_user),
) -> MFASetupResponse:
    """Generate new RFC 6238 TOTP secret and QR URI."""
    secret = generate_totp_secret()
    _pending_mfa_secrets[current_user.id] = secret
    uri = get_totp_uri(secret=secret, user_email=current_user.email, issuer="FIRA")

    return MFASetupResponse(
        secret=secret,
        otpauth_uri=uri,
        instructions="Scan this URI with your authenticator app (Google Authenticator, Microsoft Authenticator, 1Password) and submit code to /mfa/verify.",
    )

@router.post("/mfa/verify", response_model=MFAVerifyResponse)
def verify_mfa_setup(
    request: Request,
    payload: MFAVerifyRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MFAVerifyResponse:
    """Confirm MFA setup with valid code, encrypt secret at rest, and generate backup codes."""
    pending_secret = _pending_mfa_secrets.get(current_user.id)
    if not pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA setup found. Please call /mfa/setup first.",
        )

    if not verify_totp_code(pending_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid confirmation code. Ensure clock is synchronized.",
        )

    # Encrypt secret at rest
    current_user.mfa_secret_encrypted = encrypt_secret(pending_secret)
    _pending_mfa_secrets.pop(current_user.id, None)

    backup_codes = generate_backup_codes(count=8)

    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="AUTH_MFA_ENABLED",
        entity_type="app_user",
        entity_id=str(current_user.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return MFAVerifyResponse(
        status="enabled",
        backup_codes=backup_codes,
    )
