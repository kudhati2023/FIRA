import uuid
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fira.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, JSON_TYPE, UUID_TYPE

class Client(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "client"

    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trading_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tin_raw: Mapped[str] = mapped_column(String(50), nullable=False)
    tin_normalised: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    vat_category: Mapped[str] = mapped_column(String(10), default="C", nullable=False)
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    default_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    retention_months_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="clients")
    branches: Mapped[list["ClientBranch"]] = relationship("ClientBranch", back_populates="client", cascade="all, delete-orphan")
    engagements: Mapped[list["Engagement"]] = relationship("Engagement", back_populates="client", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "ix_client_tenant_tin_active",
            "tenant_id",
            "tin_normalised",
            unique=True,
            postgresql_where=text("deleted_at IS NULL")
        ),
    )

class ClientBranch(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "client_branch"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    device_serials_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=list, nullable=False)

    client: Mapped["Client"] = relationship("Client", back_populates="branches")
