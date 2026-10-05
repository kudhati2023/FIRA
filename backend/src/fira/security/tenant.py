import uuid
from dataclasses import dataclass
from fastapi import HTTPException, status
from fira.models.tenant import UserRole

@dataclass
class TenantContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    role: UserRole

    def check_access(self, target_tenant_id: uuid.UUID) -> None:
        """Enforce strict tenant isolation (HC-6)."""
        if self.tenant_id != target_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security Violation: Access to cross-tenant resource is strictly prohibited."
            )
