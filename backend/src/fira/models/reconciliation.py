import enum
import uuid
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import (
    String, Integer, BigInteger, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fira.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, JSON_TYPE, UUID_TYPE

class ExceptionClass(str, enum.Enum):
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"
    E6 = "E6"
    E7 = "E7"

class ExceptionStatus(str, enum.Enum):
    OPEN = "OPEN"
    NOTIFIED = "NOTIFIED"
    SUPPLIER_ACKNOWLEDGED = "SUPPLIER_ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    UNRECOVERABLE = "UNRECOVERABLE"
    DISMISSED = "DISMISSED"

class SupplierOutcome(str, enum.Enum):
    PENDING = "PENDING"
    CORRECTED = "CORRECTED"
    REFUSED = "REFUSED"
    NO_RESPONSE = "NO_RESPONSE"
    PARTIAL = "PARTIAL"

class Match(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "match"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    ap_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("ap_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    zimra_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("zimra_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    pass_id: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="matches")
    ap_line: Mapped["APLine"] = relationship("APLine", back_populates="match")
    zimra_line: Mapped["ZIMRALine"] = relationship("ZIMRALine", back_populates="match")

    __table_args__ = (
        UniqueConstraint("engagement_id", "ap_line_id", name="uq_match_engagement_ap_line"),
        UniqueConstraint("engagement_id", "zimra_line_id", name="uq_match_engagement_zimra_line"),
    )

class Supplier(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "supplier"

    tin_normalised: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name_norm: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    actions: Mapped[list["SupplierAction"]] = relationship("SupplierAction", back_populates="supplier")

    __table_args__ = (
        UniqueConstraint("tenant_id", "tin_normalised", name="uq_supplier_tenant_tin"),
    )

class ExceptionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "exception"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    ap_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("ap_line.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    zimra_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("zimra_line.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    match_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("match.id", ondelete="SET NULL"),
        nullable=True
    )
    primary_class: Mapped[ExceptionClass] = mapped_column(
        Enum(ExceptionClass, name="exception_class_enum", create_type=False),
        nullable=False,
        index=True
    )
    all_classes_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=list, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    vat_at_risk_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    is_recoverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_advisory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("supplier.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus, name="exception_status_enum", create_type=False),
        default=ExceptionStatus.OPEN,
        nullable=False,
        index=True
    )
    override_of_class: Mapped[Optional[ExceptionClass]] = mapped_column(
        Enum(ExceptionClass, name="exception_class_enum", create_type=False),
        nullable=True
    )
    override_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    overridden_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )
    overridden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="exceptions")

class SupplierAction(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "supplier_action"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("supplier.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    letter_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_summary: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    outcome: Mapped[SupplierOutcome] = mapped_column(
        Enum(SupplierOutcome, name="supplier_outcome_enum", create_type=False),
        default=SupplierOutcome.PENDING,
        nullable=False
    )
    exception_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=list, nullable=False)

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="actions")
