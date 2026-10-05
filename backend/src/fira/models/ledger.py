import enum
import uuid
from datetime import date
from typing import Optional, Any
from sqlalchemy import (
    String, Integer, BigInteger, Date, Boolean,
    ForeignKey, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fira.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin, JSON_TYPE, UUID_TYPE

class DocumentType(str, enum.Enum):
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"

class LineStatus(str, enum.Enum):
    OK = "OK"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    EXCLUDED = "EXCLUDED"

class APLine(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "ap_line"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    import_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("import_batch.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_name_norm: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    supplier_tin_raw: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    supplier_tin_norm: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    invoice_number_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_number_norm: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type_enum", create_type=False),
        default=DocumentType.INVOICE,
        nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    net_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    vat_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    gross_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    expense_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[LineStatus] = mapped_column(
        Enum(LineStatus, name="line_status_enum", create_type=False),
        default=LineStatus.OK,
        nullable=False
    )
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="ap_lines")
    match: Mapped[Optional["Match"]] = relationship("Match", back_populates="ap_line", uselist=False)

class ZIMRALine(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    __tablename__ = "zimra_line"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        ForeignKey("engagement.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    import_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE,
        ForeignKey("import_batch.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_name_norm: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    supplier_tin_raw: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    supplier_tin_norm: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    invoice_number_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_number_norm: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type_enum", create_type=False),
        default=DocumentType.INVOICE,
        nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    net_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    vat_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    gross_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    buyer_name_raw: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    buyer_tin_raw: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    buyer_tin_norm: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    buyer_vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    validity_status_raw: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    validity_is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    receipt_global_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fiscal_day_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[LineStatus] = mapped_column(
        Enum(LineStatus, name="line_status_enum", create_type=False),
        default=LineStatus.OK,
        nullable=False
    )
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)

    engagement: Mapped["Engagement"] = relationship("Engagement", back_populates="zimra_lines")
    match: Mapped[Optional["Match"]] = relationship("Match", back_populates="zimra_line", uselist=False)
