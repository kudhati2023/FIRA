from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces OWASP-recommended HTTP security headers
    and prevents caching of sensitive financial/reconciliation data.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # 1. Transport Security (HSTS)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

        # 2. Prevent MIME Sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 3. Clickjacking Protection
        response.headers["X-Frame-Options"] = "DENY"

        # 4. Content Security Policy (CSP)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        # 5. Referrer Information Protection
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 6. Restrict Sensitive Browser Features
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # 7. Cross-Origin Protections
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        # 8. Cache-Control for API Endpoints (prevent caching sensitive tax/ledger data)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # 9. Server Banner Scrubbing
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response
