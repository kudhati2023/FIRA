from typing import Callable, Sequence
from fastapi import HTTPException, status
from fira.models.tenant import AppUser, UserRole

# Role hierarchy: ADMIN > REVIEWER > OPERATOR
ROLE_HIERARCHY = {
    UserRole.ADMIN: 3,
    UserRole.REVIEWER: 2,
    UserRole.OPERATOR: 1,
}

def has_sufficient_privilege(user_role: UserRole, required_roles: Sequence[UserRole]) -> bool:
    """Check if user role matches one of required roles or has higher hierarchical privilege."""
    if user_role in required_roles:
        return True
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    min_required_level = min((ROLE_HIERARCHY.get(r, 999) for r in required_roles), default=999)
    return user_level >= min_required_level

def require_roles(*allowed_roles: UserRole) -> Callable[[AppUser], AppUser]:
    """FastAPI dependency to enforce Role-Based Access Control."""
    def role_checker(current_user: AppUser) -> AppUser:
        if not has_sufficient_privilege(current_user.role, allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role: {current_user.role.value}. Required: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return role_checker
