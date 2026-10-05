import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fira.main import app
from fira.models import Base, Tenant, AppUser, UserRole
from fira.db.session import get_db
from fira.security.crypto import hash_password
from fira.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    is_token_revoked,
)
from fira.api.auth import _reset_failed_attempts
from fira.security.rate_limiter import reset_rate_limits

from sqlalchemy.pool import StaticPool

client = TestClient(app)

@pytest.fixture
def mock_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
    session = TestingSession()

    # Seed tenant and user
    tenant = Tenant(name="Test Tenant", slug="test-corp")
    session.add(tenant)
    session.commit()

    hashed = hash_password("ValidPassword#2026!")
    user = AppUser(
        tenant_id=tenant.id,
        email="testuser@example.com",
        full_name="Test Enterprise User",
        role=UserRole.ADMIN,
        password_hash=hashed,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.close()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield None, tenant, user
    app.dependency_overrides.clear()

def test_jwt_token_lifecycle():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email="operator@test.local",
        role="OPERATOR",
        expires_delta=timedelta(minutes=15),
    )
    decoded = decode_token(token)
    assert decoded["sub"] == user_id
    assert decoded["tenant_id"] == tenant_id
    assert decoded["role"] == "OPERATOR"
    assert "jti" in decoded
    assert decoded["token_type"] == "access"

def test_jwt_revocation():
    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, tenant_id=tenant_id, email="a@b.com", role="ADMIN")
    decoded = decode_token(token)
    jti = decoded["jti"]

    assert is_token_revoked(jti) is False
    revoke_token(jti)
    assert is_token_revoked(jti) is True

    with pytest.raises(Exception):
        decode_token(token)

def test_auth_login_and_profile_flow(mock_db):
    session, tenant, user = mock_db
    _reset_failed_attempts(user.email)

    # 1. Login with valid credentials
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "ValidPassword#2026!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "testuser@example.com"

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    # 2. Access /me endpoint with Bearer token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "testuser@example.com"
    assert me_data["tenant_name"] == "Test Tenant"

    # 3. Refresh token
    ref_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_resp.status_code == 200
    ref_data = ref_resp.json()
    assert "access_token" in ref_data

    # 4. Logout (revokes access token)
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200

    # 5. Access /me with revoked token is rejected
    denied = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert denied.status_code == 401

def test_login_failure_and_account_lockout(mock_db):
    session, tenant, user = mock_db
    _reset_failed_attempts(user.email)
    reset_rate_limits()

    # 4 consecutive invalid attempts
    for _ in range(4):
        reset_rate_limits()
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "testuser@example.com", "password": "WrongPassword123!"},
        )
        assert resp.status_code == 401

    # 5th attempt triggers lockout
    reset_rate_limits()
    resp5 = client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "WrongPassword123!"},
    )
    # Either 401 on 5th or 423 on lockout
    assert resp5.status_code in (401, 423)

    # Next attempt is locked out with HTTP 423
    reset_rate_limits()
    locked_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "ValidPassword#2026!"},
    )
    assert locked_resp.status_code == 423
    assert "locked" in locked_resp.json()["detail"].lower()

    _reset_failed_attempts(user.email)
    reset_rate_limits()
