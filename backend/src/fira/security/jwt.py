import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set
import jwt
import redis
from fira.config import settings

# In-memory revocation cache fallback (e.g. for testing or when Redis is offline)
_local_revoked_tokens: Set[str] = set()
_redis_client_cached: Optional[redis.Redis] = None
_redis_checked: bool = False

def _get_redis_client() -> Optional[redis.Redis]:
    global _redis_client_cached, _redis_checked
    if _redis_checked:
        return _redis_client_cached
    if settings.ENVIRONMENT in ("testing", "test"):
        _redis_checked = True
        return None
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=0.2)
        r.ping()
        _redis_client_cached = r
    except Exception:
        _redis_client_cached = None
    _redis_checked = True
    return _redis_client_cached

def is_token_revoked(jti: str) -> bool:
    """Check if token ID has been explicitly revoked."""
    if jti in _local_revoked_tokens:
        return True
    client = _get_redis_client()
    if client:
        try:
            return bool(client.exists(f"revoked_token:{jti}"))
        except Exception:
            pass
    return False

def revoke_token(jti: str, ttl_seconds: int = 86400) -> None:
    """Add token ID to revocation blacklist with TTL."""
    _local_revoked_tokens.add(jti)
    client = _get_redis_client()
    if client:
        try:
            client.setex(f"revoked_token:{jti}", max(ttl_seconds, 60), "revoked")
        except Exception:
            pass

def create_access_token(
    user_id: str,
    tenant_id: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[Dict[str, Any]] = None
) -> str:
    """Create signed enterprise JWT access token with tenant and role claims."""
    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = str(uuid.uuid4())

    payload: Dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
        "token_type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(
    user_id: str,
    tenant_id: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create signed enterprise JWT refresh token with unique JTI."""
    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    jti = str(uuid.uuid4())

    payload: Dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
        "token_type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and cryptographically verify JWT.
    Raises jwt.PyJWTError on invalid or expired token.
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "exp", "iat", "jti"]},
    )
    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise jwt.InvalidTokenError("Token has been revoked")
    return payload
