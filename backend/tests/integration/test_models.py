import uuid
from datetime import date, datetime
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from fira.models import (
    Base, Tenant, AppUser, UserRole, Client, ClientBranch,
    Engagement, ImportBatch, MappingProfile, EngagementMetric,
    EngagementType, EngagementStatus, SourceType,
    APLine, ZIMRALine, DocumentType, LineStatus,
    Match, ExceptionModel, Supplier, SupplierAction,
    ExceptionClass, ExceptionStatus, SupplierOutcome,
    VATRatePeriod, ConfigSetting, ReportArtifact, AuditLog,
    ReportArtifactKind
)

@pytest.fixture
def db_session():
    # In-memory SQLite for fast testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

def test_tenant_and_user_creation(db_session):
    tenant = Tenant(name="Test Audit Practice", slug="test-practice")
    db_session.add(tenant)
    db_session.commit()

    user = AppUser(
        tenant_id=tenant.id,
        email="test@audit.local",
        password_hash="hashed_pw_123",
        full_name="Jane Doe",
        role=UserRole.ADMIN
    )
    db_session.add(user)
    db_session.commit()

    queried_user = db_session.execute(select(AppUser).where(AppUser.email == "test@audit.local")).scalar_one()
    assert queried_user.full_name == "Jane Doe"
    assert queried_user.tenant.slug == "test-practice"

def test_vat_rate_period_resolution(db_session):
    # Seed 2025 (15%) and 2026 (15.5%) rates (HC-3)
    p1 = VATRatePeriod(
        jurisdiction="ZW",
        rate_basis_points=1500,
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        note="15% standard rate"
    )
    p2 = VATRatePeriod(
        jurisdiction="ZW",
        rate_basis_points=1550,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        note="15.5% standard rate"
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    def resolve_vat_rate(tx_date: date, jur: str = "ZW") -> int:
        stmt = select(VATRatePeriod).where(
            VATRatePeriod.jurisdiction == jur,
            VATRatePeriod.effective_from <= tx_date,
            (VATRatePeriod.effective_to.is_(None) | (VATRatePeriod.effective_to >= tx_date))
        )
        period = db_session.execute(stmt).scalar_one()
        return period.rate_basis_points

    assert resolve_vat_rate(date(2025, 12, 15)) == 1500  # 15.0%
    assert resolve_vat_rate(date(2026, 1, 1)) == 1550    # 15.5%
    assert resolve_vat_rate(date(2026, 8, 20)) == 1550   # 15.5%

def test_full_engagement_lifecycle_data_model(db_session):
    # Create Tenant
    tenant = Tenant(name="Alpha Corp Audit", slug="alpha")
    db_session.add(tenant)
    db_session.commit()

    # Create Client & Branch
    client = Client(
        tenant_id=tenant.id,
        legal_name="Delta Beverages Ltd",
        trading_name="Delta",
        tin_raw="200-111-222",
        tin_normalised="200111222",
        vat_number="VAT1001",
        default_currency="USD"
    )
    db_session.add(client)
    db_session.commit()

    branch = ClientBranch(
        tenant_id=tenant.id,
        client_id=client.id,
        name="Harare Main Branch"
    )
    db_session.add(branch)
    db_session.commit()

    # Create Engagement
    eng = Engagement(
        tenant_id=tenant.id,
        client_id=client.id,
        reference="ENG-2026-001",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        status=EngagementStatus.DRAFT
    )
    db_session.add(eng)
    db_session.commit()

    # Create Import Batch
    batch = ImportBatch(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        source_type=SourceType.AP_LEDGER,
        original_filename="ap_ledger.xlsx",
        file_sha256="abc123def456",
        storage_key="s3://fira/ap_ledger.xlsx",
        row_count_total=10,
        row_count_accepted=10
    )
    db_session.add(batch)
    db_session.commit()

    # Create AP Line & ZIMRA Line
    ap_line = APLine(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        import_batch_id=batch.id,
        source_row_number=1,
        supplier_name_raw="Econet Wireless",
        supplier_name_norm="ECONET WIRELESS",
        supplier_tin_norm="100200300",
        invoice_number_raw="INV-001",
        invoice_number_norm="INV1",
        invoice_date=date(2026, 1, 15),
        document_type=DocumentType.INVOICE,
        currency="USD",
        net_minor=100000,
        vat_minor=15500,
        gross_minor=115500
    )
    zimra_line = ZIMRALine(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        import_batch_id=batch.id,
        source_row_number=1,
        supplier_name_raw="Econet Wireless Ltd",
        supplier_name_norm="ECONET WIRELESS",
        supplier_tin_norm="100200300",
        invoice_number_raw="INV/0001",
        invoice_number_norm="INV1",
        invoice_date=date(2026, 1, 15),
        document_type=DocumentType.INVOICE,
        currency="USD",
        net_minor=100000,
        vat_minor=15500,
        gross_minor=115500
    )
    db_session.add_all([ap_line, zimra_line])
    db_session.commit()

    # Create Match
    match = Match(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        ap_line_id=ap_line.id,
        zimra_line_id=zimra_line.id,
        pass_id="P1",
        confidence=100
    )
    db_session.add(match)
    db_session.commit()

    # Create Supplier
    supplier = Supplier(
        tenant_id=tenant.id,
        tin_normalised="100200300",
        name_norm="ECONET WIRELESS",
        display_name="Econet Wireless Zimbabwe"
    )
    db_session.add(supplier)
    db_session.commit()

    # Create Exception
    exc = ExceptionModel(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        ap_line_id=ap_line.id,
        zimra_line_id=zimra_line.id,
        match_id=match.id,
        primary_class=ExceptionClass.E5,
        rule_id="RULE_E5_VALUE_DISCREPANCY",
        vat_at_risk_minor=500,
        currency="USD",
        supplier_id=supplier.id,
        status=ExceptionStatus.OPEN
    )
    db_session.add(exc)
    db_session.commit()

    # Create Supplier Action
    action = SupplierAction(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        supplier_id=supplier.id,
        letter_ref="LTR-2026-001",
        generated_at=datetime.utcnow(),
        outcome=SupplierOutcome.PENDING
    )
    db_session.add(action)
    db_session.commit()

    # Create Report Artifact
    artifact = ReportArtifact(
        tenant_id=tenant.id,
        engagement_id=eng.id,
        revision=1,
        kind=ReportArtifactKind.EXCEPTION_REGISTER_XLSX,
        storage_key="s3://fira/reports/exc.xlsx",
        sha256="sha256hash123"
    )
    db_session.add(artifact)
    db_session.commit()

    # Create Audit Log
    audit = AuditLog(
        tenant_id=tenant.id,
        action="CREATE_ENGAGEMENT",
        entity_type="engagement",
        entity_id=str(eng.id),
        occurred_at=datetime.utcnow()
    )
    db_session.add(audit)
    db_session.commit()

    # Verify counts and relationships
    queried_eng = db_session.execute(select(Engagement).where(Engagement.id == eng.id)).scalar_one()
    assert len(queried_eng.ap_lines) == 1
    assert len(queried_eng.zimra_lines) == 1
    assert len(queried_eng.matches) == 1
    assert len(queried_eng.exceptions) == 1
    assert len(queried_eng.reports) == 1
