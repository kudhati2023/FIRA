import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fira.models import Base, Tenant, AppUser, UserRole
from fira.security.audit import log_audit_event
from fira.security.sanitizer import sanitize_data, mask_auth_header

def test_sanitizer_redacts_credentials():
    dirty_payload = {
        "user": "taxpayer@corp.zw",
        "password": "SuperSecretPassword123!",
        "nested": {
            "mfa_secret": "JBSWY3DPEHPK3PXP",
            "token": "eyJhbGciOi...",
            "normal_field": "123456789",
        },
        "list_items": [
            {"password_hash": "$argon2id$..."},
            {"safe_value": 42},
        ],
    }

    cleaned = sanitize_data(dirty_payload)
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"]["mfa_secret"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["normal_field"] == "123456789"
    assert cleaned["list_items"][0]["password_hash"] == "[REDACTED]"
    assert cleaned["list_items"][1]["safe_value"] == 42

def test_mask_auth_header():
    assert mask_auth_header("") == ""
    assert mask_auth_header("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi") == "Bearer eyJh...dWIi"
    assert mask_auth_header("Basic dXNlcjpwYXNz") == "[REDACTED]"

def test_audit_event_logging_and_integrity():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    entry = log_audit_event(
        db=db,
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        action="UPDATE_TAX_CONFIG",
        entity_type="config_setting",
        entity_id="vat_rate",
        before_json={"rate": 1500, "password_dummy": "secret123"},
        after_json={"rate": 1550},
        ip_address="192.168.1.100",
        user_agent="AuditClient/1.0",
    )
    db.commit()

    assert entry.tenant_id == tenant_id
    assert entry.actor_user_id == actor_id
    assert entry.action == "UPDATE_TAX_CONFIG"
    assert entry.before_json["password_dummy"] == "[REDACTED]"
    assert "_integrity_sha256" in entry.after_json
    assert len(entry.after_json["_integrity_sha256"]) == 64
    db.close()
