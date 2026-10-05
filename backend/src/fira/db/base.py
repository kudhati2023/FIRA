import uuid
from datetime import datetime
from sqlalchemy import text, func, ForeignKey, String, BigInteger, Boolean, DateTime, JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr

# Cross-dialect type wrappers: Native PostgreSQL JSONB in PG and JSON in SQLite; Uuid converts seamlessly across PG and SQLite
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
UUID_TYPE = Uuid(as_uuid=True)

class Base(DeclarativeBase):
    """Base declarative class for all FIRA entities."""
    pass

class TimestampMixin:
    """Provides standard UTC created_at and updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

class UUIDPrimaryKeyMixin:
    """Provides standard UUID v4 primary key."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE,
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

class TenantScopedMixin:
    """Enforces tenant isolation by attaching indexed tenant_id foreign key."""
    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID_TYPE,
            ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )
