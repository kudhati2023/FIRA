import uuid
from datetime import date
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from fira.models import (
    Base, Tenant, Client, Engagement, APLine, DocumentType
)

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

def test_tenant_isolation_repository_level(db_session):
    # Setup Tenant A and Tenant B
    tenant_a = Tenant(name="Tenant Alpha", slug="alpha")
    tenant_b = Tenant(name="Tenant Beta", slug="beta")
    db_session.add_all([tenant_a, tenant_b])
    db_session.commit()

    # Client for Tenant A
    client_a = Client(
        tenant_id=tenant_a.id,
        legal_name="Alpha Client Ltd",
        tin_raw="111111111",
        tin_normalised="111111111"
    )
    # Client for Tenant B
    client_b = Client(
        tenant_id=tenant_b.id,
        legal_name="Beta Client Ltd",
        tin_raw="222222222",
        tin_normalised="222222222"
    )
    db_session.add_all([client_a, client_b])
    db_session.commit()

    # Engagement for Tenant A
    eng_a = Engagement(
        tenant_id=tenant_a.id,
        client_id=client_a.id,
        reference="ENG-ALPHA-01",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31)
    )
    # Engagement for Tenant B
    eng_b = Engagement(
        tenant_id=tenant_b.id,
        client_id=client_b.id,
        reference="ENG-BETA-01",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31)
    )
    db_session.add_all([eng_a, eng_b])
    db_session.commit()

    # Lines for Tenant A
    ap_a = APLine(
        tenant_id=tenant_a.id,
        engagement_id=eng_a.id,
        source_row_number=1,
        supplier_name_raw="Supplier A",
        supplier_name_norm="SUPPLIER A",
        invoice_number_raw="INV-A",
        invoice_number_norm="INVA",
        invoice_date=date(2026, 1, 10),
        document_type=DocumentType.INVOICE,
        currency="USD",
        net_minor=10000,
        vat_minor=1550,
        gross_minor=11550
    )
    # Lines for Tenant B
    ap_b = APLine(
        tenant_id=tenant_b.id,
        engagement_id=eng_b.id,
        source_row_number=1,
        supplier_name_raw="Supplier B",
        supplier_name_norm="SUPPLIER B",
        invoice_number_raw="INV-B",
        invoice_number_norm="INVB",
        invoice_date=date(2026, 1, 10),
        document_type=DocumentType.INVOICE,
        currency="USD",
        net_minor=20000,
        vat_minor=3100,
        gross_minor=23100
    )
    db_session.add_all([ap_a, ap_b])
    db_session.commit()

    # Query scoped to Tenant A must NEVER return Tenant B records (HC-6)
    def query_clients(tenant_id: uuid.UUID):
        return db_session.execute(
            select(Client).where(Client.tenant_id == tenant_id)
        ).scalars().all()

    def query_engagements(tenant_id: uuid.UUID):
        return db_session.execute(
            select(Engagement).where(Engagement.tenant_id == tenant_id)
        ).scalars().all()

    def query_lines(tenant_id: uuid.UUID):
        return db_session.execute(
            select(APLine).where(APLine.tenant_id == tenant_id)
        ).scalars().all()

    # Verify Tenant A scope
    clients_a = query_clients(tenant_a.id)
    assert len(clients_a) == 1
    assert clients_a[0].legal_name == "Alpha Client Ltd"

    engs_a = query_engagements(tenant_a.id)
    assert len(engs_a) == 1
    assert engs_a[0].reference == "ENG-ALPHA-01"

    lines_a = query_lines(tenant_a.id)
    assert len(lines_a) == 1
    assert lines_a[0].invoice_number_norm == "INVA"

    # Verify Tenant B scope
    clients_b = query_clients(tenant_b.id)
    assert len(clients_b) == 1
    assert clients_b[0].legal_name == "Beta Client Ltd"

    engs_b = query_engagements(tenant_b.id)
    assert len(engs_b) == 1
    assert engs_b[0].reference == "ENG-BETA-01"

    lines_b = query_lines(tenant_b.id)
    assert len(lines_b) == 1
    assert lines_b[0].invoice_number_norm == "INVB"
