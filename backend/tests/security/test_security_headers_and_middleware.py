import pytest
from fastapi.testclient import TestClient
from fira.main import app
from fira.config import settings
from fira.security.rate_limiter import reset_rate_limits

client = TestClient(app)

def test_enterprise_security_headers_present():
    resp = client.get("/healthz")
    assert resp.status_code == 200

    headers = resp.headers
    # 1. HSTS
    assert "strict-transport-security" in headers
    assert "max-age=63072000" in headers["strict-transport-security"]

    # 2. Prevent MIME sniffing
    assert headers.get("x-content-type-options") == "nosniff"

    # 3. Frame options
    assert headers.get("x-frame-options") == "DENY"

    # 4. Content Security Policy
    assert "content-security-policy" in headers
    assert "default-src 'self'" in headers["content-security-policy"]

    # 5. Referrer Policy
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    # 6. Permissions Policy
    assert "permissions-policy" in headers
    assert "camera=()" in headers["permissions-policy"]

    # 7. Request ID correlation
    assert "x-request-id" in headers

def test_request_id_forwarding():
    custom_id = "custom-trace-uuid-12345"
    resp = client.get("/healthz", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == custom_id

def test_api_cache_control_headers():
    # Endpoints under /api/ must have sensitive cache-control headers
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.local", "password": "DummyPassword#2026!"},
    )
    headers = resp.headers
    assert "cache-control" in headers
    assert "no-store" in headers["cache-control"]
    assert "no-cache" in headers["cache-control"]
    assert headers.get("pragma") == "no-cache"

def test_rate_limiting_enforcement():
    reset_rate_limits()

    # The auth limit is 5 requests per minute
    limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
    responses = []
    for _ in range(limit + 3):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@test.local", "password": "DummyPassword#2026!"},
        )
        responses.append(r)

    # At least the requests beyond the limit should get HTTP 429
    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes
    last_resp = responses[-1]
    assert last_resp.status_code == 429
    assert "retry-after" in last_resp.headers

    reset_rate_limits()
