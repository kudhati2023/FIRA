import time
from collections import defaultdict
from typing import Dict, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import redis

from fira.config import settings

# In-memory sliding window storage: key -> list of float timestamps
_memory_windows: Dict[str, List[float]] = defaultdict(list)

_redis_client_cached: Optional[redis.Redis] = None
_redis_checked: bool = False

def _get_redis() -> Optional[redis.Redis]:
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

def is_rate_limited(key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
    """
    Check if rate limit is exceeded for key within window.
    Returns (is_limited, retry_after_seconds).
    """
    now = time.time()
    cutoff = now - window_seconds

    # 1. Try Redis sliding window
    r = _get_redis()
    if r:
        try:
            pipe = r.pipeline()
            redis_key = f"rate_limit:{key}"
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_seconds + 5)
            _, _, count, _ = pipe.execute()
            if count > limit:
                return True, int(window_seconds)
            return False, 0
        except Exception:
            pass

    # 2. In-memory sliding window fallback
    timestamps = _memory_windows[key]
    # Prune old entries
    _memory_windows[key] = [t for t in timestamps if t > cutoff]
    if len(_memory_windows[key]) >= limit:
        oldest = _memory_windows[key][0]
        retry_after = max(1, int(oldest + window_seconds - now))
        return True, retry_after

    _memory_windows[key].append(now)
    return False, 0

def reset_rate_limits() -> None:
    """Utility to clear in-memory limits (used in test suites)."""
    _memory_windows.clear()

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Enterprise rate limiting middleware mitigating brute force, DDoS, and scraping.
    Applies strict limits to authentication endpoints and standard limits to API routes.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.ENABLE_RATE_LIMITER:
            return await call_next(request)

        path = request.url.path

        # Health checks must never be rate-limited
        if path in ("/healthz", "/readyz", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Determine rate limit profile
        if "/auth/login" in path or "/auth/mfa" in path:
            limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
            key = f"auth:{client_ip}"
        else:
            limit = settings.API_RATE_LIMIT_PER_MINUTE
            key = f"api:{client_ip}"

        limited, retry_after = is_rate_limited(key, limit=limit, window_seconds=60)
        if limited:
            return JSONResponse(
                status_code=429,
                content={
                    "type": "https://errors.fira.local/rate-limit-exceeded",
                    "title": "Rate Limit Exceeded",
                    "status": 429,
                    "detail": f"Too many requests. Please retry in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
