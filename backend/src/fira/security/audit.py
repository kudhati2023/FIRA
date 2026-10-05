import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from fira.models.system import AuditLog
from fira.security.crypto import compute_audit_hash
from fira.security.sanitizer import sanitize_data

logger = logging.getLogger("fira.audit")

def log_audit_event(
    db: Session,
    tenant_id: uuid.UUID,
    action: str,
    entity_type: str,
    actor_user_id: Optional[uuid.UUID] = None,
    entity_id: Optional[str] = None,
    before_json: Optional[Dict[str, Any]] = None,
    after_json: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Persist tamper-evident, sanitized enterprise audit event to database.
    Complies with SOC 2 / ISO 27001 non-repudiation and traceability requirements.
    """
    occurred_at = datetime.now(timezone.utc)
    sanitized_before = sanitize_data(before_json) if before_json else None
    sanitized_after = sanitize_data(after_json) if after_json else None

    # Compute tamper-evident integrity hash
    audit_hash = compute_audit_hash(
        tenant_id=str(tenant_id),
        actor_id=str(actor_user_id) if actor_user_id else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp_iso=occurred_at.isoformat(),
        before_state=json.dumps(sanitized_before, sort_keys=True) if sanitized_before else None,
        after_state=json.dumps(sanitized_after, sort_keys=True) if sanitized_after else None,
    )

    # Store integrity hash in metadata within after_json or dedicated record
    if sanitized_after is None:
        sanitized_after = {}
    sanitized_after["_integrity_sha256"] = audit_hash

    entry = AuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=sanitized_before,
        after_json=sanitized_after,
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else None,
        occurred_at=occurred_at,
    )

    db.add(entry)
    db.flush()

    logger.info(
        "AUDIT_EVENT: action=%s entity_type=%s entity_id=%s tenant=%s actor=%s hash=%s",
        action,
        entity_type,
        entity_id,
        tenant_id,
        actor_user_id,
        audit_hash,
    )
    return entry
