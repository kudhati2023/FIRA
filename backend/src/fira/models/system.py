import enum
import uuid
from datetime import date, datetime
from typing import Optional, Any
from sqlalchemy import (
    String, Integer, Date, DateTime, ForeignKey, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fira.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, JSON_TYPE, UUID_TYPE

class ReportArtifactKind(str, enum.Enum):
    EXCEPTION_REGISTER_XLSX = "EXCEPTION_REGISTER_XLSX"
    FINDINGS_PACK_PDF = "FINDINGS_PACK_PDF"
    SUPPLIER_LETTER_DOCX = "SUPPLIER_LETTER_DOCX"
    SUPPLIER_LETTER_PDF = "SUPPLIER_LETTER_PDF"
    METRICS_CSV = "METRICS_CSV"

class VATRatePeriod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vat_rate_period"

    jurisdiction: Mapped[str] = mapped_column(String(10), default="ZW", nullable=False, index=True)
    rate_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)  # 1500 = 15%, 1550 = 15.5%
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

class ConfigSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "config_setting"

    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

class ReportArtifact(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "report_artifact"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    kind: Mapped[ReportArtifactKind] = mapped_column(
        Enum(ReportArtifactKind, name="report_artifact_kind_enum", create_type=False),
        nullable=False,
        index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="reports")

class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "audit_log"

    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    before_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON_TYPE, nullable=True)
    after_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON_TYPE, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
