import uuid
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fira.config import settings

def _create_engine():
    if settings.ENVIRONMENT in ("testing", "test") or "sqlite" in settings.DATABASE_URL:
        return create_engine("sqlite:///:memory:")

    urls_to_try = [settings.DATABASE_URL]
    if "postgresql+psycopg://" in settings.DATABASE_URL:
        urls_to_try.append(settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql+psycopg2://"))

    for url in urls_to_try:
        try:
            eng = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10, connect_args={"connect_timeout": 1})
            with eng.connect() as conn:
                pass
            return eng
        except Exception:
            continue

    # Graceful fallback to persistent local SQLite database file when running outside Docker
    return create_engine("sqlite:///fira_local.db", connect_args={"check_same_thread": False})

engine = _create_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def set_tenant_context(session: Session, tenant_id: uuid.UUID) -> None:
    """Set PostgreSQL transaction-local setting for Row-Level Security (RLS)."""
    session.execute(
        text("SET LOCAL app.tenant_id = :tenant_id"),
        {"tenant_id": str(tenant_id)}
    )

def get_tenant_db(tenant_id: uuid.UUID) -> Generator[Session, None, None]:
    """Provide a database session pre-scoped with tenant RLS context."""
    db = SessionLocal()
    try:
        set_tenant_context(db, tenant_id)
        yield db
    finally:
        db.close()
