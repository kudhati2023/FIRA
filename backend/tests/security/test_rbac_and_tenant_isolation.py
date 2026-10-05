import uuid
import pytest
from fastapi import HTTPException
from fira.models.tenant import AppUser, UserRole
from fira.security.rbac import has_sufficient_privilege, require_roles
from fira.security.tenant import TenantContext

def test_rbac_privilege_hierarchy():
    # ADMIN has full access to ADMIN, REVIEWER, OPERATOR
    assert has_sufficient_privilege(UserRole.ADMIN, [UserRole.ADMIN]) is True
    assert has_sufficient_privilege(UserRole.ADMIN, [UserRole.REVIEWER]) is True
    assert has_sufficient_privilege(UserRole.ADMIN, [UserRole.OPERATOR]) is True

    # REVIEWER has access to REVIEWER and OPERATOR, but not ADMIN
    assert has_sufficient_privilege(UserRole.REVIEWER, [UserRole.REVIEWER]) is True
    assert has_sufficient_privilege(UserRole.REVIEWER, [UserRole.OPERATOR]) is True
    assert has_sufficient_privilege(UserRole.REVIEWER, [UserRole.ADMIN]) is False

    # OPERATOR only has access to OPERATOR
    assert has_sufficient_privilege(UserRole.OPERATOR, [UserRole.OPERATOR]) is True
    assert has_sufficient_privilege(UserRole.OPERATOR, [UserRole.REVIEWER]) is False
    assert has_sufficient_privilege(UserRole.OPERATOR, [UserRole.ADMIN]) is False

def test_require_roles_dependency():
    admin_checker = require_roles(UserRole.ADMIN)
    reviewer_checker = require_roles(UserRole.REVIEWER)

    admin_user = AppUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@corp.local",
        full_name="Admin",
        role=UserRole.ADMIN,
        password_hash="dummy",
    )
    operator_user = AppUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="op@corp.local",
        full_name="Operator",
        role=UserRole.OPERATOR,
        password_hash="dummy",
    )

    # Admin passes both
    assert admin_checker(admin_user) == admin_user
    assert reviewer_checker(admin_user) == admin_user

    # Operator is denied admin access with HTTP 403
    with pytest.raises(HTTPException) as exc_info:
        admin_checker(operator_user)
    assert exc_info.value.status_code == 403
    assert "not permitted" in exc_info.value.detail.lower()

def test_tenant_context_isolation_guard_hc6():
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    ctx = TenantContext(
        tenant_id=tenant_a_id,
        user_id=uuid.uuid4(),
        email="user@tenant-a.com",
        role=UserRole.OPERATOR,
    )

    # Access within own tenant succeeds
    ctx.check_access(tenant_a_id)

    # Access across different tenant raises HTTP 403 (HC-6)
    with pytest.raises(HTTPException) as exc_info:
        ctx.check_access(tenant_b_id)
    assert exc_info.value.status_code == 403
    assert "cross-tenant" in exc_info.value.detail.lower()
