from datetime import date, datetime, timezone
from decimal import Decimal
import io
import re
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from fira.db.session import get_db
from fira.engine.normalisation import (
    normalise_invoice_number,
    normalise_supplier_name,
    normalise_tin,
)

def normalise_string(raw: Optional[str]) -> str:
    return normalise_supplier_name(raw)[0]

def strip_company_suffixes(raw: Optional[str]) -> str:
    return normalise_supplier_name(raw)[1]
from fira.engine.reconciler import reconcile
from fira.engine.types import (
    ClientParticulars,
    DocumentType as EngineDocType,
    LineStatus as EngineLineStatus,
    MatchConfig,
    NormalisedLine,
)
from fira.models.client import Client
from fira.models.engagement import (
    Engagement,
    EngagementStatus,
    EngagementType,
    ImportBatch,
    SourceType,
)
from fira.models.ledger import APLine, DocumentType, LineStatus, ZIMRALine
from fira.models.reconciliation import (
    ExceptionClass,
    ExceptionModel,
    ExceptionStatus,
    Match,
    Supplier,
    SupplierAction,
    SupplierOutcome,
)
from fira.models.tenant import AppUser
from fira.security.audit import log_audit_event
from fira.security.dependencies import get_current_user
from fira.security.file_validator import validate_uploaded_file
from fira.engine.file_ingestion import parse_ap_ledger_file, parse_zimra_claim_file

router = APIRouter(prefix="/api/v1/engagements", tags=["Engagements & Reconciliation"])

class IngestRecognizedDocRequest(BaseModel):
    supplier_name: str
    supplier_tin: Optional[str] = None
    invoice_number: str
    invoice_date: str
    currency: str = "USD"
    net_amount: float
    vat_amount: float
    gross_amount: float
    expense_category: Optional[str] = "Scanned Tax Invoice"

# --- Schemas ---

class EngagementCreate(BaseModel):
    client_id: uuid.UUID
    reference: str = Field(..., min_length=2, max_length=100)
    period_start: date
    period_end: date
    currency: str = Field(default="USD", max_length=3)
    engagement_type: str = Field(default="AUDIT")

class EngagementSummary(BaseModel):
    id: uuid.UUID
    reference: str
    client_id: uuid.UUID
    client_name: str
    client_tin: str
    period_start: date
    period_end: date
    currency: str
    status: str
    ap_lines_count: int
    zimra_lines_count: int
    matches_count: int
    exceptions_count: int
    vat_at_risk_by_currency: Dict[str, float]

class MatchItem(BaseModel):
    id: uuid.UUID
    pass_id: str
    confidence: int
    supplier_name: str
    invoice_number: str
    invoice_date: str
    currency: str
    ap_gross: float
    zimra_gross: float
    ap_vat: float
    zimra_vat: float

class ExceptionItem(BaseModel):
    id: uuid.UUID
    primary_class: str
    rule_id: str
    vat_at_risk: float
    currency: str
    is_recoverable: bool
    is_advisory: bool
    status: str
    supplier_name: str
    invoice_number: str
    invoice_date: str
    evidence: Dict[str, Any]

class SupplierLetterRequest(BaseModel):
    supplier_name: str
    supplier_tin: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None

class SupplierLetterResponse(BaseModel):
    letter_ref: str
    generated_at: str
    supplier_name: str
    supplier_tin: str
    recipient_email: str
    vat_at_risk: float
    currency: str
    invoices_affected: List[Dict[str, Any]]
    letter_text: str


# --- Routes ---

@router.get("", response_model=List[EngagementSummary])
def list_engagements(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[EngagementSummary]:
    """List all engagements for current tenant with line counts and VAT-at-risk totals."""
    stmt = (
        select(Engagement)
        .where(Engagement.tenant_id == current_user.tenant_id)
        .order_by(Engagement.created_at.desc())
    )
    engagements = db.execute(stmt).scalars().all()

    summaries = []
    for eng in engagements:
        client = db.execute(select(Client).where(Client.id == eng.client_id)).scalar_one()

        ap_count = db.scalar(
            select(func.count(APLine.id)).where(APLine.engagement_id == eng.id)
        ) or 0
        zimra_count = db.scalar(
            select(func.count(ZIMRALine.id)).where(ZIMRALine.engagement_id == eng.id)
        ) or 0
        matches_count = db.scalar(
            select(func.count(Match.id)).where(Match.engagement_id == eng.id)
        ) or 0

        # Exceptions & VAT at risk
        exc_stmt = select(ExceptionModel).where(ExceptionModel.engagement_id == eng.id)
        exceptions = db.execute(exc_stmt).scalars().all()

        vat_by_curr: Dict[str, float] = {}
        for ex in exceptions:
            if not ex.is_advisory:
                vat_by_curr[ex.currency] = vat_by_curr.get(ex.currency, 0.0) + (ex.vat_at_risk_minor / 100.0)

        summaries.append(
            EngagementSummary(
                id=eng.id,
                reference=eng.reference,
                client_id=client.id,
                client_name=client.legal_name,
                client_tin=client.tin_normalised,
                period_start=eng.period_start,
                period_end=eng.period_end,
                currency=eng.currency,
                status=eng.status.value,
                ap_lines_count=ap_count,
                zimra_lines_count=zimra_count,
                matches_count=matches_count,
                exceptions_count=len(exceptions),
                vat_at_risk_by_currency=vat_by_curr,
            )
        )
    return summaries

@router.post("", response_model=EngagementSummary, status_code=status.HTTP_201_CREATED)
def create_engagement(
    payload: EngagementCreate,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngagementSummary:
    """Create a new VAT input tax reconciliation engagement."""
    # Verify client belongs to current tenant
    client = db.execute(
        select(Client).where(Client.id == payload.client_id, Client.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found in tenant")

    # Check for duplicate reference in tenant
    dup = db.execute(
        select(Engagement).where(
            Engagement.tenant_id == current_user.tenant_id,
            Engagement.reference == payload.reference.strip(),
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Engagement reference already exists")

    eng = Engagement(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        client_id=client.id,
        reference=payload.reference.strip(),
        period_start=payload.period_start,
        period_end=payload.period_end,
        currency=payload.currency.upper(),
        engagement_type=EngagementType(payload.engagement_type.upper()),
        status=EngagementStatus.DRAFT,
        operator_id=current_user.id,
    )
    db.add(eng)
    db.flush()

    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="ENGAGEMENT_CREATED",
        entity_type="engagement",
        entity_id=str(eng.id),
        after_json={"reference": eng.reference, "client": client.legal_name},
    )
    db.commit()

    return EngagementSummary(
        id=eng.id,
        reference=eng.reference,
        client_id=client.id,
        client_name=client.legal_name,
        client_tin=client.tin_normalised,
        period_start=eng.period_start,
        period_end=eng.period_end,
        currency=eng.currency,
        status=eng.status.value,
        ap_lines_count=0,
        zimra_lines_count=0,
        matches_count=0,
        exceptions_count=0,
        vat_at_risk_by_currency={},
    )

@router.post("/{id}/seed-sample")
@router.post("/{id}/seed-sample-data")
def seed_sample_engagement_data(
    id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Populate realistic Zimbabwean AP and ZIMRA lines for rapid demonstration
    and manual test of P1-P5 matching passes and E1-E7 exception detection.
    """
    eng = db.execute(
        select(Engagement).where(Engagement.id == id, Engagement.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    client = db.execute(select(Client).where(Client.id == eng.client_id)).scalar_one()

    # Clear previous lines for clean seed
    db.execute(delete(Match).where(Match.engagement_id == eng.id))
    db.execute(delete(ExceptionModel).where(ExceptionModel.engagement_id == eng.id))
    db.execute(delete(APLine).where(APLine.engagement_id == eng.id))
    db.execute(delete(ZIMRALine).where(ZIMRALine.engagement_id == eng.id))
    db.flush()

    # Realistic mock test fixtures:
    sample_ap_data = [
        # Line 1: Exact match with Delta Beverages (P1 Exact)
        {
            "row": 1, "supplier": "Delta Beverages Limited", "tin": "100012345",
            "inv": "INV-DB-9081", "date": date(2026, 1, 10), "curr": "USD",
            "net": 100000, "vat": 15500, "gross": 115500, "cat": "Inventory"
        },
        # Line 2: Econet Wireless invoice (P2 - slight invoice number format difference: EC-8801 vs EC8801)
        {
            "row": 2, "supplier": "Econet Wireless Zimbabwe", "tin": "100098765",
            "inv": "EC-8801", "date": date(2026, 1, 12), "curr": "USD",
            "net": 50000, "vat": 7750, "gross": 57750, "cat": "Telecommunications"
        },
        # Line 3: National Foods (P3 - date drift of 2 days between ledger and ZIMRA fiscal record)
        {
            "row": 3, "supplier": "National Foods Ltd", "tin": "100033445",
            "inv": "NF-2026-104", "date": date(2026, 1, 15), "curr": "USD",
            "net": 250000, "vat": 38750, "gross": 288750, "cat": "Raw Materials"
        },
        # Line 4: Olivine (P4 - fuzzy supplier name: Olivine Industries vs Olivine Ind.)
        {
            "row": 4, "supplier": "Olivine Industries (Pvt) Ltd", "tin": "100055667",
            "inv": "OLV-5542", "date": date(2026, 1, 18), "curr": "USD",
            "net": 80000, "vat": 12400, "gross": 92400, "cat": "Supplies"
        },
        # Line 5: Simbisa Brands (E1 - Missing from ZIMRA! Supplier never fiscalised invoice)
        {
            "row": 5, "supplier": "Simbisa Brands Zimbabwe", "tin": "100077889",
            "inv": "SIM-9912", "date": date(2026, 1, 20), "curr": "USD",
            "net": 120000, "vat": 18600, "gross": 138600, "cat": "Catering"
        },
        # Line 6: Zimplats Transport (E5 - Value / VAT discrepancy: Claimed $4,650 VAT, ZIMRA reported $3,100)
        {
            "row": 6, "supplier": "Zimplats Logistics", "tin": "100066778",
            "inv": "ZMP-7721", "date": date(2026, 1, 22), "curr": "USD",
            "net": 300000, "vat": 46500, "gross": 346500, "cat": "Freight"
        },
        # Line 7: Meikles Hotel Golf Club (E7 - Non-qualifying entertainment expense advisory)
        {
            "row": 7, "supplier": "Meikles Hospitality Club", "tin": "100044556",
            "inv": "MK-3310", "date": date(2026, 1, 25), "curr": "USD",
            "net": 40000, "vat": 6200, "gross": 46200, "cat": "Golf & Hospitality lunch"
        },
        # Line 8: ZWG Currency Segregated Transaction (FR-VAL-4)
        {
            "row": 8, "supplier": "ZESA Electricity Supply", "tin": "100022119",
            "inv": "ZESA-8001", "date": date(2026, 1, 28), "curr": "ZWG",
            "net": 1500000, "vat": 232500, "gross": 1732500, "cat": "Utilities"
        },
    ]

    sample_zimra_data = [
        # ZIMRA 1: Matches AP Line 1 (Delta)
        {
            "row": 1, "supplier": "Delta Beverages Limited", "tin": "100012345",
            "inv": "INV-DB-9081", "date": date(2026, 1, 10), "curr": "USD",
            "net": 100000, "vat": 15500, "gross": 115500,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 2: Matches AP Line 2 (Econet - format difference)
        {
            "row": 2, "supplier": "Econet Wireless Zimbabwe", "tin": "100098765",
            "inv": "EC8801", "date": date(2026, 1, 12), "curr": "USD",
            "net": 50000, "vat": 7750, "gross": 57750,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 3: Matches AP Line 3 (National Foods - 2 day drift)
        {
            "row": 3, "supplier": "National Foods Ltd", "tin": "100033445",
            "inv": "NF-2026-104", "date": date(2026, 1, 17), "curr": "USD",
            "net": 250000, "vat": 38750, "gross": 288750,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 4: Matches AP Line 4 (Olivine - fuzzy name)
        {
            "row": 4, "supplier": "Olivine Ind.", "tin": "100055667",
            "inv": "OLV-5542", "date": date(2026, 1, 18), "curr": "USD",
            "net": 80000, "vat": 12400, "gross": 92400,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 5: Matches AP Line 6 (Zimplats - amount mismatch)
        {
            "row": 5, "supplier": "Zimplats Logistics", "tin": "100066778",
            "inv": "ZMP-7721", "date": date(2026, 1, 22), "curr": "USD",
            "net": 200000, "vat": 31000, "gross": 231000,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 6: Matches AP Line 7 (Meikles Club - entertainment)
        {
            "row": 6, "supplier": "Meikles Hospitality Club", "tin": "100044556",
            "inv": "MK-3310", "date": date(2026, 1, 25), "curr": "USD",
            "net": 40000, "vat": 6200, "gross": 46200,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 7: Matches AP Line 8 (ZESA ZWG)
        {
            "row": 7, "supplier": "ZESA Electricity Supply", "tin": "100022119",
            "inv": "ZESA-8001", "date": date(2026, 1, 28), "curr": "ZWG",
            "net": 1500000, "vat": 232500, "gross": 1732500,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": True
        },
        # ZIMRA 8: Marked Invalid in ZIMRA fiscal system (E4)
        {
            "row": 8, "supplier": "Chiredzi Hardware Supplies", "tin": "100099112",
            "inv": "CH-1002", "date": date(2026, 1, 29), "curr": "USD",
            "net": 60000, "vat": 9300, "gross": 69300,
            "buyer_name": client.legal_name, "buyer_tin": client.tin_normalised, "is_valid": False
        },
    ]

    # Save AP Lines
    for d in sample_ap_data:
        ap = APLine(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            engagement_id=eng.id,
            source_row_number=d["row"],
            supplier_name_raw=d["supplier"],
            supplier_name_norm=normalise_string(d["supplier"]),
            supplier_tin_raw=d["tin"],
            supplier_tin_norm=normalise_tin(d["tin"]),
            invoice_number_raw=d["inv"],
            invoice_number_norm=normalise_invoice_number(d["inv"]),
            invoice_date=d["date"],
            currency=d["curr"],
            net_minor=d["net"],
            vat_minor=d["vat"],
            gross_minor=d["gross"],
            expense_category=d["cat"],
            description=f"Ledger record for {d['cat']}",
            status=LineStatus.OK,
        )
        db.add(ap)

    # Save ZIMRA Lines
    for d in sample_zimra_data:
        zimra = ZIMRALine(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            engagement_id=eng.id,
            source_row_number=d["row"],
            supplier_name_raw=d["supplier"],
            supplier_name_norm=normalise_string(d["supplier"]),
            supplier_tin_raw=d["tin"],
            supplier_tin_norm=normalise_tin(d["tin"]),
            invoice_number_raw=d["inv"],
            invoice_number_norm=normalise_invoice_number(d["inv"]),
            invoice_date=d["date"],
            currency=d["curr"],
            net_minor=d["net"],
            vat_minor=d["vat"],
            gross_minor=d["gross"],
            buyer_name_raw=d["buyer_name"],
            buyer_tin_raw=d["buyer_tin"],
            buyer_tin_norm=normalise_tin(d["buyer_tin"]),
            validity_is_valid=d["is_valid"],
            validity_status_raw="VALID" if d["is_valid"] else "CANCELLED_INVALID",
            status=LineStatus.OK,
        )
        db.add(zimra)

    eng.status = EngagementStatus.INGESTING
    db.commit()

    return {
        "status": "success",
        "message": f"Seeded {len(sample_ap_data)} AP ledger lines and {len(sample_zimra_data)} ZIMRA claim lines into engagement {eng.reference}.",
        "ap_lines_count": len(sample_ap_data),
        "zimra_lines_count": len(sample_zimra_data),
    }

@router.post("/{id}/upload-ap")
async def upload_ap_ledger(
    id: uuid.UUID,
    file: UploadFile = File(...),
    replace_existing: bool = Form(default=False),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ingest actual AP Purchase Ledger file (.csv, .xlsx, .xls) into engagement.
    """
    eng = db.execute(
        select(Engagement).where(Engagement.id == id, Engagement.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    clean_name, ext = validate_uploaded_file(file.filename, file.file)

    parsed_lines = parse_ap_ledger_file(file.file, ext, default_currency=eng.currency)
    if not parsed_lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readable AP ledger lines found in uploaded file")

    if replace_existing:
        db.execute(delete(Match).where(Match.engagement_id == eng.id))
        db.execute(delete(ExceptionModel).where(ExceptionModel.engagement_id == eng.id))
        db.execute(delete(APLine).where(APLine.engagement_id == eng.id))
        db.flush()

    batch = ImportBatch(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        engagement_id=eng.id,
        source_type=SourceType.AP_LEDGER,
        original_filename=clean_name,
        storage_key=f"tenants/{current_user.tenant_id}/engagements/{eng.id}/ap_{clean_name}",
        file_sha256="manual_upload",
        row_count_total=len(parsed_lines),
        row_count_accepted=len(parsed_lines),
        uploaded_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    current_max_row = db.execute(
        select(func.coalesce(func.max(APLine.source_row_number), 0)).where(APLine.engagement_id == eng.id)
    ).scalar() or 0

    for idx, d in enumerate(parsed_lines):
        ap = APLine(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            engagement_id=eng.id,
            import_batch_id=batch.id,
            source_row_number=current_max_row + idx + 1,
            supplier_name_raw=d["supplier_name_raw"],
            supplier_name_norm=d["supplier_name_norm"],
            supplier_tin_raw=d["supplier_tin_raw"],
            supplier_tin_norm=d["supplier_tin_norm"],
            invoice_number_raw=d["invoice_number_raw"],
            invoice_number_norm=d["invoice_number_norm"],
            invoice_date=d["invoice_date"],
            currency=d["currency"],
            net_minor=d["net_minor"],
            vat_minor=d["vat_minor"],
            gross_minor=d["gross_minor"],
            expense_category=d["expense_category"],
            description=d["description"],
            status=LineStatus.OK,
            raw_json={},
        )
        db.add(ap)

    eng.status = EngagementStatus.INGESTING
    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="AP_LEDGER_FILE_INGESTED",
        entity_type="engagement",
        entity_id=str(eng.id),
        after_json={"filename": clean_name, "lines_ingested": len(parsed_lines)},
    )
    db.commit()

    total_count = db.execute(select(func.count(APLine.id)).where(APLine.engagement_id == eng.id)).scalar() or 0

    return {
        "status": "success",
        "message": f"Successfully ingested {len(parsed_lines)} AP ledger lines from '{clean_name}'.",
        "lines_ingested": len(parsed_lines),
        "total_ap_lines": total_count,
    }


@router.post("/{id}/upload-zimra")
async def upload_zimra_export(
    id: uuid.UUID,
    file: UploadFile = File(...),
    replace_existing: bool = Form(default=False),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ingest official ZIMRA FDMS Claim List export file (.csv, .xlsx, .xls) into engagement.
    Strictly file-based per HC-1 and HC-2.
    """
    eng = db.execute(
        select(Engagement).where(Engagement.id == id, Engagement.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    client = db.execute(select(Client).where(Client.id == eng.client_id)).scalar_one()

    clean_name, ext = validate_uploaded_file(file.filename, file.file)

    parsed_lines = parse_zimra_claim_file(
        file_stream=file.file,
        ext=ext,
        default_currency=eng.currency,
        client_name=client.legal_name,
        client_tin=client.tin_normalised,
    )
    if not parsed_lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readable ZIMRA claim lines found in uploaded file")

    if replace_existing:
        db.execute(delete(Match).where(Match.engagement_id == eng.id))
        db.execute(delete(ExceptionModel).where(ExceptionModel.engagement_id == eng.id))
        db.execute(delete(ZIMRALine).where(ZIMRALine.engagement_id == eng.id))
        db.flush()

    batch = ImportBatch(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        engagement_id=eng.id,
        source_type=SourceType.ZIMRA_CLAIM_LIST,
        original_filename=clean_name,
        storage_key=f"tenants/{current_user.tenant_id}/engagements/{eng.id}/zimra_{clean_name}",
        file_sha256="manual_upload",
        row_count_total=len(parsed_lines),
        row_count_accepted=len(parsed_lines),
        uploaded_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    current_max_row = db.execute(
        select(func.coalesce(func.max(ZIMRALine.source_row_number), 0)).where(ZIMRALine.engagement_id == eng.id)
    ).scalar() or 0

    for idx, d in enumerate(parsed_lines):
        zimra = ZIMRALine(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            engagement_id=eng.id,
            import_batch_id=batch.id,
            source_row_number=current_max_row + idx + 1,
            supplier_name_raw=d["supplier_name_raw"],
            supplier_name_norm=d["supplier_name_norm"],
            supplier_tin_raw=d["supplier_tin_raw"],
            supplier_tin_norm=d["supplier_tin_norm"],
            invoice_number_raw=d["invoice_number_raw"],
            invoice_number_norm=d["invoice_number_norm"],
            invoice_date=d["invoice_date"],
            currency=d["currency"],
            net_minor=d["net_minor"],
            vat_minor=d["vat_minor"],
            gross_minor=d["gross_minor"],
            buyer_name_raw=d["buyer_name_raw"],
            buyer_tin_raw=d["buyer_tin_raw"],
            buyer_tin_norm=d["buyer_tin_norm"],
            validity_is_valid=d["validity_is_valid"],
            validity_status_raw=d["validity_status_raw"],
            status=LineStatus.OK,
            raw_json={},
        )
        db.add(zimra)

    eng.status = EngagementStatus.INGESTING
    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="ZIMRA_CLAIM_FILE_INGESTED",
        entity_type="engagement",
        entity_id=str(eng.id),
        after_json={"filename": clean_name, "lines_ingested": len(parsed_lines)},
    )
    db.commit()

    total_count = db.execute(select(func.count(ZIMRALine.id)).where(ZIMRALine.engagement_id == eng.id)).scalar() or 0

    return {
        "status": "success",
        "message": f"Successfully ingested {len(parsed_lines)} ZIMRA claim lines from '{clean_name}'.",
        "lines_ingested": len(parsed_lines),
        "total_zimra_lines": total_count,
    }


@router.post("/{id}/ingest-recognized-document")
def ingest_recognized_invoice_into_engagement(
    id: uuid.UUID,
    payload: IngestRecognizedDocRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Directly ingest an auto-recognized scanned invoice/receipt as an APLine
    in the selected engagement.
    """
    eng = db.execute(
        select(Engagement).where(Engagement.id == id, Engagement.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    try:
        inv_date = datetime.strptime(payload.invoice_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        inv_date = date.today()

    current_max_row = db.execute(
        select(func.coalesce(func.max(APLine.source_row_number), 0)).where(APLine.engagement_id == eng.id)
    ).scalar() or 0

    net_minor = int(round(payload.net_amount * 100))
    vat_minor = int(round(payload.vat_amount * 100))
    gross_minor = int(round(payload.gross_amount * 100))

    ap = APLine(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        engagement_id=eng.id,
        source_row_number=current_max_row + 1,
        supplier_name_raw=payload.supplier_name.strip(),
        supplier_name_norm=normalise_string(payload.supplier_name),
        supplier_tin_raw=payload.supplier_tin,
        supplier_tin_norm=normalise_tin(payload.supplier_tin) if payload.supplier_tin else None,
        invoice_number_raw=payload.invoice_number.strip(),
        invoice_number_norm=normalise_invoice_number(payload.invoice_number),
        invoice_date=inv_date,
        currency=payload.currency.upper(),
        net_minor=net_minor,
        vat_minor=vat_minor,
        gross_minor=gross_minor,
        expense_category=payload.expense_category or "Scanned Tax Invoice",
        description=f"Auto-recognized scanned invoice {payload.invoice_number}",
        status=LineStatus.OK,
        raw_json={"source": "document_scanner"},
    )
    db.add(ap)
    db.commit()

    total_count = db.execute(select(func.count(APLine.id)).where(APLine.engagement_id == eng.id)).scalar() or 0

    return {
        "status": "success",
        "message": f"Ingested scanned invoice '{payload.invoice_number}' for {payload.supplier_name} into engagement {eng.reference}.",
        "ap_line_id": str(ap.id),
        "total_ap_lines": total_count,
    }

@router.post("/{id}/reconcile")
def run_reconciliation(
    id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Execute deterministic reconciliation engine (HC-4):
    1. Multi-pass matching passes P1 to P5
    2. Exception classification E1 to E7
    3. Currency segregation (FR-VAL-4)
    Persists Match and Exception records.
    """
    eng = db.execute(
        select(Engagement).where(Engagement.id == id, Engagement.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    client = db.execute(select(Client).where(Client.id == eng.client_id)).scalar_one()

    # Load lines
    ap_db_lines = db.execute(select(APLine).where(APLine.engagement_id == eng.id)).scalars().all()
    zimra_db_lines = db.execute(select(ZIMRALine).where(ZIMRALine.engagement_id == eng.id)).scalars().all()

    if not ap_db_lines:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No AP ledger lines found to reconcile")

    # Map to engine NormalisedLine
    ap_engine = [
        NormalisedLine(
            line_id=str(line.id),
            source_row_number=line.source_row_number,
            supplier_name_raw=line.supplier_name_raw,
            supplier_name_norm=line.supplier_name_norm,
            supplier_name_stripped=strip_company_suffixes(line.supplier_name_norm),
            supplier_tin_raw=line.supplier_tin_raw,
            supplier_tin_norm=line.supplier_tin_norm,
            invoice_number_raw=line.invoice_number_raw,
            invoice_number_norm=line.invoice_number_norm,
            invoice_date=line.invoice_date,
            document_type=EngineDocType.INVOICE,
            currency=line.currency,
            net_minor=line.net_minor,
            vat_minor=line.vat_minor,
            gross_minor=line.gross_minor,
            expense_category=line.expense_category,
            description=line.description,
            status=EngineLineStatus.OK,
        )
        for line in ap_db_lines
    ]

    zimra_engine = [
        NormalisedLine(
            line_id=str(line.id),
            source_row_number=line.source_row_number,
            supplier_name_raw=line.supplier_name_raw,
            supplier_name_norm=line.supplier_name_norm,
            supplier_name_stripped=strip_company_suffixes(line.supplier_name_norm),
            supplier_tin_raw=line.supplier_tin_raw,
            supplier_tin_norm=line.supplier_tin_norm,
            invoice_number_raw=line.invoice_number_raw,
            invoice_number_norm=line.invoice_number_norm,
            invoice_date=line.invoice_date,
            document_type=EngineDocType.INVOICE,
            currency=line.currency,
            net_minor=line.net_minor,
            vat_minor=line.vat_minor,
            gross_minor=line.gross_minor,
            buyer_name_raw=line.buyer_name_raw,
            buyer_name_norm=normalise_string(line.buyer_name_raw or ""),
            buyer_tin_raw=line.buyer_tin_raw,
            buyer_tin_norm=line.buyer_tin_norm,
            validity_is_valid=line.validity_is_valid,
            validity_status_raw=line.validity_status_raw,
            status=EngineLineStatus.OK,
        )
        for line in zimra_db_lines
    ]

    client_part = ClientParticulars(
        client_id=str(client.id),
        legal_name_norm=client.tin_normalised,
        trading_name_norm=normalise_string(client.trading_name or client.legal_name),
        tin_normalised=client.tin_normalised,
        vat_number=client.vat_number,
    )

    # Run deterministic reconciliation (HC-4)
    result = reconcile(
        ap_lines=ap_engine,
        zimra_lines=zimra_engine,
        client=client_part,
        config=MatchConfig(),
    )

    # Clear old results
    db.execute(delete(Match).where(Match.engagement_id == eng.id))
    db.execute(delete(ExceptionModel).where(ExceptionModel.engagement_id == eng.id))
    db.flush()

    # Save matches
    for m in result.matches:
        match_record = Match(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            engagement_id=eng.id,
            ap_line_id=uuid.UUID(m.ap_line.line_id),
            zimra_line_id=uuid.UUID(m.zimra_line.line_id),
            pass_id=m.pass_id,
            confidence=m.confidence,
            is_manual=m.is_manual,
            note=m.note,
        )
        db.add(match_record)

    # Save exceptions
    for ex in result.exceptions:
        exc_model = ExceptionModel(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            engagement_id=eng.id,
            ap_line_id=uuid.UUID(ex.ap_line.line_id) if ex.ap_line else None,
            zimra_line_id=uuid.UUID(ex.zimra_line.line_id) if ex.zimra_line else None,
            primary_class=ExceptionClass(ex.primary_class.value),
            all_classes_json=[c.value for c in ex.all_classes],
            rule_id=ex.rule_id,
            evidence_json=ex.evidence,
            vat_at_risk_minor=ex.vat_at_risk_minor,
            currency=ex.currency,
            is_recoverable=ex.is_recoverable,
            is_advisory=ex.is_advisory,
            status=ExceptionStatus.OPEN,
        )
        db.add(exc_model)

    eng.status = EngagementStatus.REVIEW
    db.commit()

    return {
        "status": "completed",
        "stats": {
            "total_ap_lines": result.stats.total_ap_lines,
            "total_zimra_lines": result.stats.total_zimra_lines,
            "matched_count": result.stats.matched_count,
            "ap_only_count": result.stats.ap_only_count,
            "zimra_only_count": result.stats.zimra_only_count,
            "exceptions_count": result.stats.exceptions_count,
            "vat_at_risk_by_currency": {
                curr: amount / 100.0 for curr, amount in result.stats.vat_at_risk_by_currency.items()
            },
            "duration_ms": result.stats.execution_duration_ms,
        },
    }

@router.get("/{id}/matches", response_model=List[MatchItem])
def get_engagement_matches(
    id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[MatchItem]:
    """Retrieve matched line pairs for this engagement."""
    matches = db.execute(
        select(Match).where(Match.engagement_id == id, Match.tenant_id == current_user.tenant_id)
    ).scalars().all()

    items = []
    for m in matches:
        ap = db.execute(select(APLine).where(APLine.id == m.ap_line_id)).scalar_one()
        zimra = db.execute(select(ZIMRALine).where(ZIMRALine.id == m.zimra_line_id)).scalar_one()

        items.append(
            MatchItem(
                id=m.id,
                pass_id=m.pass_id,
                confidence=m.confidence,
                supplier_name=ap.supplier_name_raw,
                invoice_number=ap.invoice_number_raw,
                invoice_date=ap.invoice_date.isoformat(),
                currency=ap.currency,
                ap_gross=ap.gross_minor / 100.0,
                zimra_gross=zimra.gross_minor / 100.0,
                ap_vat=ap.vat_minor / 100.0,
                zimra_vat=zimra.vat_minor / 100.0,
            )
        )
    return items

@router.get("/{id}/exceptions", response_model=List[ExceptionItem])
def get_engagement_exceptions(
    id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ExceptionItem]:
    """Retrieve categorized exception records for this engagement."""
    exceptions = db.execute(
        select(ExceptionModel).where(ExceptionModel.engagement_id == id, ExceptionModel.tenant_id == current_user.tenant_id)
        .order_by(ExceptionModel.vat_at_risk_minor.desc())
    ).scalars().all()

    items = []
    for ex in exceptions:
        ap = db.execute(select(APLine).where(APLine.id == ex.ap_line_id)).scalar_one_or_none() if ex.ap_line_id else None
        zimra = db.execute(select(ZIMRALine).where(ZIMRALine.id == ex.zimra_line_id)).scalar_one_or_none() if ex.zimra_line_id else None

        supplier_name = (ap.supplier_name_raw if ap else (zimra.supplier_name_raw if zimra else "Unknown"))
        inv_number = (ap.invoice_number_raw if ap else (zimra.invoice_number_raw if zimra else "N/A"))
        inv_date = (ap.invoice_date.isoformat() if ap else (zimra.invoice_date.isoformat() if zimra else "N/A"))

        items.append(
            ExceptionItem(
                id=ex.id,
                primary_class=ex.primary_class.value,
                rule_id=ex.rule_id,
                vat_at_risk=ex.vat_at_risk_minor / 100.0,
                currency=ex.currency,
                is_recoverable=ex.is_recoverable,
                is_advisory=ex.is_advisory,
                status=ex.status.value,
                supplier_name=supplier_name,
                invoice_number=inv_number,
                invoice_date=inv_date,
                evidence=ex.evidence_json,
            )
        )
    return items

@router.get("/{id}/suppliers")
def get_affected_suppliers(
    id: uuid.UUID,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Aggregate exceptions by supplier with total VAT at risk."""
    exceptions = db.execute(
        select(ExceptionModel).where(
            ExceptionModel.engagement_id == id,
            ExceptionModel.tenant_id == current_user.tenant_id,
            ExceptionModel.is_advisory == False,
        )
    ).scalars().all()

    supplier_map: Dict[str, Dict[str, Any]] = {}
    for ex in exceptions:
        ap = db.execute(select(APLine).where(APLine.id == ex.ap_line_id)).scalar_one_or_none() if ex.ap_line_id else None
        name = ap.supplier_name_raw if ap else "Unknown Supplier"
        tin = ap.supplier_tin_norm if ap and ap.supplier_tin_norm else "N/A"

        if name not in supplier_map:
            supplier_map[name] = {
                "supplier_name": name,
                "supplier_tin": tin,
                "total_vat_at_risk": 0.0,
                "currency": ex.currency,
                "exception_count": 0,
                "invoices": [],
            }

        supplier_map[name]["total_vat_at_risk"] += (ex.vat_at_risk_minor / 100.0)
        supplier_map[name]["exception_count"] += 1
        if ap:
            supplier_map[name]["invoices"].append({
                "invoice_number": ap.invoice_number_raw,
                "date": ap.invoice_date.isoformat(),
                "gross": ap.gross_minor / 100.0,
                "vat": ap.vat_minor / 100.0,
                "exception_class": ex.primary_class.value,
            })

    return list(supplier_map.values())

@router.post("/{id}/supplier-letters", response_model=SupplierLetterResponse)
def generate_supplier_letter(
    id: uuid.UUID,
    payload: SupplierLetterRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupplierLetterResponse:
    """
    Generate formal tax invoice correction notice letter requesting supplier
    to verify and fiscalise unrecorded or discrepant VAT transactions.
    """
    eng = db.execute(
        select(Engagement).where(Engagement.id == id, Engagement.tenant_id == current_user.tenant_id)
    ).scalar_one_or_none()
    if not eng:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    client = db.execute(select(Client).where(Client.id == eng.client_id)).scalar_one()

    # Find exceptions for this supplier
    exceptions = db.execute(
        select(ExceptionModel).where(
            ExceptionModel.engagement_id == eng.id,
            ExceptionModel.tenant_id == current_user.tenant_id,
        )
    ).scalars().all()

    affected_invoices = []
    total_vat = 0.0
    curr = "USD"
    for ex in exceptions:
        ap = db.execute(select(APLine).where(APLine.id == ex.ap_line_id)).scalar_one_or_none() if ex.ap_line_id else None
        if ap and payload.supplier_name.lower() in ap.supplier_name_raw.lower():
            total_vat += ex.vat_at_risk_minor / 100.0
            curr = ex.currency
            affected_invoices.append({
                "invoice_number": ap.invoice_number_raw,
                "date": ap.invoice_date.isoformat(),
                "gross": ap.gross_minor / 100.0,
                "vat": ap.vat_minor / 100.0,
                "discrepancy": ex.primary_class.value,
            })

    letter_ref = f"LTR-{eng.reference}-{uuid.uuid4().hex[:6].upper()}"
    today_str = date.today().strftime("%d %B %Y")

    letter_text = (
        f"DATE: {today_str}\n"
        f"REFERENCE: {letter_ref}\n\n"
        f"TO: The Accounts Receivable Manager\n"
        f"    {payload.supplier_name}\n"
        f"    TIN: {payload.supplier_tin or 'Recorded upon file'}\n\n"
        f"FROM: {client.legal_name}\n"
        f"      TIN: {client.tin_normalised}\n"
        f"      VAT Category: {client.vat_category}\n\n"
        f"RE: URGENT — REQUEST FOR VAT FISCALISATION / RE-ISSUANCE OF TAX INVOICES\n\n"
        f"Dear Sir / Madam,\n\n"
        f"In accordance with Section 15(2) of the Zimbabwe Value Added Tax Act [Chapter 23:12], "
        f"our organization has performed a reconciliation of input tax claims against invoice records "
        f"exported from the ZIMRA Fiscal Data Management System (FDMS) for the period {eng.period_start} to {eng.period_end}.\n\n"
        f"During this review, our systems identified {len(affected_invoices)} invoice(s) with total VAT of "
        f"{curr} {total_vat:,.2f} issued by {payload.supplier_name} that do not appear in our ZIMRA claim list or contain "
        f"fiscal status discrepancies (e.g. absent from FDMS gateway, invalid fiscal day signature, or value mismatch).\n\n"
        f"A summary of the affected transaction(s) is detailed below:\n"
    )

    for inv in affected_invoices:
        letter_text += f"  - Invoice #{inv['invoice_number']} dated {inv['date']}: Gross {curr} {inv['gross']:,.2f}, VAT {curr} {inv['vat']:,.2f} [Exception: {inv['discrepancy']}]\n"

    letter_text += (
        f"\nTo ensure full statutory compliance and allow proper input tax deduction, kindly verify your FDMS fiscal device transmission "
        f"and supply us with verified fiscal tax invoices or credit/debit adjustments within 14 business days.\n\n"
        f"Yours faithfully,\n\n"
        f"Head of Finance & Tax Compliance\n"
        f"{client.legal_name}\n"
    )

    return SupplierLetterResponse(
        letter_ref=letter_ref,
        generated_at=datetime.now(timezone.utc).isoformat(),
        supplier_name=payload.supplier_name,
        supplier_tin=payload.supplier_tin or "N/A",
        recipient_email=payload.contact_email or "accounts@supplier.local",
        vat_at_risk=total_vat,
        currency=curr,
        invoices_affected=affected_invoices,
        letter_text=letter_text,
    )
