import enum
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fira.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, JSON_TYPE, UUID_TYPE

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"
    OPERATOR = "OPERATOR"

class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    retention_months: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list["AppUser"]] = relationship("AppUser", back_populates="tenant", cascade="all, delete-orphan")
    clients: Mapped[list["Client"]] = relationship("Client", back_populates="tenant", cascade="all, delete-orphan")

class AppUser(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "app_user"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", create_type=False),
        default=UserRole.OPERATOR,
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_secret_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
