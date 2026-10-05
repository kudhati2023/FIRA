import enum
import uuid
from datetime import date, datetime
from typing import Optional, Any
from sqlalchemy import (
    String, Integer, BigInteger, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Enum, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fira.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, JSON_TYPE, UUID_TYPE

class EngagementType(str, enum.Enum):
    AUDIT = "AUDIT"
    RETAINER_MONTHLY = "RETAINER_MONTHLY"

class EngagementStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    INGESTING = "INGESTING"
    RECONCILING = "RECONCILING"
    REVIEW = "REVIEW"
    REPORTED = "REPORTED"
    CLOSED = "CLOSED"

class SourceType(str, enum.Enum):
    AP_LEDGER = "AP_LEDGER"
    ZIMRA_CLAIM_LIST = "ZIMRA_CLAIM_LIST"
    MANUAL_ENTRY = "MANUAL_ENTRY"

class Engagement(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "engagement"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    vat_category: Mapped[str] = mapped_column(String(10), default="C", nullable=False)
    engagement_type: Mapped[EngagementType] = mapped_column(
        Enum(EngagementType, name="engagement_type_enum", create_type=False),
        default=EngagementType.AUDIT,
        nullable=False
    )
    status: Mapped[EngagementStatus] = mapped_column(
        Enum(EngagementStatus, name="engagement_status_enum", create_type=False),
        default=EngagementStatus.DRAFT,
        nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    operator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )
    reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )
    fee_quoted_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    fee_accepted_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    reported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=list, nullable=False)

    client: Mapped["Client"] = relationship("Client", back_populates="engagements")
    import_batches: Mapped[list["ImportBatch"]] = relationship("ImportBatch", back_populates="engagement", cascade="all, delete-orphan")
    ap_lines: Mapped[list["APLine"]] = relationship("APLine", back_populates="engagement", cascade="all, delete-orphan")
    zimra_lines: Mapped[list["ZIMRALine"]] = relationship("ZIMRALine", back_populates="engagement", cascade="all, delete-orphan")
    matches: Mapped[list["Match"]] = relationship("Match", back_populates="engagement", cascade="all, delete-orphan")
    exceptions: Mapped[list["ExceptionModel"]] = relationship("ExceptionModel", back_populates="engagement", cascade="all, delete-orphan")
    metrics: Mapped[list["EngagementMetric"]] = relationship("EngagementMetric", back_populates="engagement", cascade="all, delete-orphan")
    reports: Mapped[list["ReportArtifact"]] = relationship("ReportArtifact", back_populates="engagement", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "reference", name="uq_engagement_tenant_reference"),
    )

class ImportBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "import_batch"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", create_type=False),
        nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    row_count_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mapping_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("mapping_profile.id", ondelete="SET NULL"),
        nullable=True
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="PROCESSED", nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="import_batches")

    __table_args__ = (
        UniqueConstraint("engagement_id", "file_sha256", name="uq_import_batch_engagement_sha256"),
    )

class MappingProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "mapping_profile"

    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", create_type=False),
        nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    header_signature: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    column_map_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

class EngagementMetric(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "engagement_metric"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    captured_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True
    )

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="metrics")
