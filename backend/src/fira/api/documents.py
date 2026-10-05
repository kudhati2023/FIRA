import io
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fira.api.engagements import EngagementSummary
from fira.config import MANDATORY_SCOPE_DISCLAIMER
from fira.db.session import get_db
from fira.engine.document_intelligence import (
    extract_entities_from_document_text,
    extract_text_from_pdf_bytes,
    resolve_or_propose_client,
    evaluate_statutory_and_fiscal_validity,
)
from fira.models.client import Client
from fira.models.engagement import Engagement, EngagementStatus, EngagementType
from fira.models.tenant import AppUser
from fira.security.audit import log_audit_event
from fira.security.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/documents", tags=["Document Intelligence & Auto-Onboarding"])


# --- Schemas ---

class RecognizeDocumentRequest(BaseModel):
    raw_text: Optional[str] = Field(default=None, description="Raw text of scanned invoice or OCR stream")
    preset_name: Optional[str] = Field(default=None, description="Pre-packaged scanned invoice template name")

class RecognizeDocumentResponse(BaseModel):
    buyer_name: str
    buyer_tin: str
    buyer_vat_number: Optional[str] = None
    supplier_name: str
    supplier_tin: str
    invoice_number: str
    invoice_date: str
    currency: str
    city: str
    net_amount: float
    vat_amount: float
    gross_amount: float
    confidence_score: int
    resolution: Dict[str, Any]
    fiscal_details: Dict[str, Any] = Field(default_factory=dict)
    realtime_validation: Dict[str, Any] = Field(default_factory=dict)
    zimra_portal_url: str = "https://fdms.zimra.co.zw/verify"
    notice: str = MANDATORY_SCOPE_DISCLAIMER

class AutoOnboardRequest(BaseModel):
    buyer_name: str
    buyer_tin: str
    currency: str = "USD"
    vat_category: str = "C"
    city: Optional[str] = "Harare"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
    gross_amount: Optional[float] = None
    vat_amount: Optional[float] = None


# Pre-packaged Zimbabwean Scanned Invoice Demo Fixtures
DEMO_SCANNED_INVOICES = {
    "delta_beverages": """
TAX INVOICE — FISCAL RECIPIENT
Delta Beverages Limited
Sutherland Road, Workington, Harare, Zimbabwe
TIN: 100012345 | VAT No: 10023456 | Fiscal Device: FP-ZW-88902 | Fiscal Day: 42
Verification Code: DB-998812

DATE: 10 January 2026
INVOICE NO: INV-DB-9081

CUSTOMER / BILL TO:
Delta Corporation Limited
1 Nelson Mandela Avenue, Harare
TIN: 200012345
VAT Category: C
City: Harare

Line Item Description: 500 cases Beverage Concentrate
Net Amount: USD 1,000.00
VAT (15.5%): USD 155.00
TOTAL AMOUNT DUE: USD 1,155.00
ZIMRA Verification URL: https://fdms.zimra.co.zw/verify?code=DB-998812&tin=100012345&inv=INV-DB-9081
""",
    "national_foods": """
TAX INVOICE
National Foods Limited
10 Stirling Road, Heavy Industrial Sites, Harare
TIN: 100033445 | VAT No: 10044556 | Fiscal Device: NF-FDMS-302 | Fiscal Day: 104
Verification Code: NF-774411

DATE: 15 January 2026
INVOICE NO: NF-2026-104

BUYER:
National Foods Holdings Ltd
Harare, Zimbabwe
TIN: 200033889
VAT Category: C

Description: Bulk Wheat & Grain Milling Supplies
Net Amount: USD 2,500.00
VAT (15.5%): USD 387.50
TOTAL GROSS: USD 2,887.50
ZIMRA Verification URL: https://fdms.zimra.co.zw/verify?code=NF-774411&tin=100033445&inv=NF-2026-104
""",
    "econet_telecom": """
TAX INVOICE / FISCAL TAX MEMORANDUM
Econet Wireless Zimbabwe Limited
Econet Park, 2 Old Mutare Road, Msasa, Harare
TIN: 100098765 | VAT No: 10077889 | Fiscal Device: EW-SVR-0199 | Fiscal Day: 89
Verification Code: EC-552200

DATE: 12 January 2026
INVOICE NO: EC-8801

CLIENT:
Delta Corporation Limited
Harare, Zimbabwe
TIN: 200012345

Description: Dedicated High-Speed Fiber Internet & APN
Net Amount: USD 500.00
VAT (15.5%): USD 77.50
TOTAL DUE: USD 577.50
ZIMRA Verification URL: https://fdms.zimra.co.zw/verify?code=EC-552200&tin=100098765&inv=EC-8801
""",
    "zesa_electricity": """
ZIMBABWE ELECTRICITY TRANSMISSION & DISTRIBUTION CO (ZETDC)
TAX INVOICE
TIN: 100022119 | VAT No: 10099887 | Fiscal Device: ZETDC-SVR-77 | Fiscal Day: 28
Verification Code: ZE-441199

DATE: 28 January 2026
INVOICE NO: ZESA-8001

CUSTOMER:
Olivine Industries (Pvt) Ltd
Birmingham Road, Southerton, Harare
TIN: 200055778
VAT Category: C

Description: Maximum Demand Industrial Power Supply
Net Amount: ZWG 15,000.00
VAT (15.5%): ZWG 2,325.00
GROSS TOTAL: ZWG 17,325.00
ZIMRA Verification URL: https://fdms.zimra.co.zw/verify?code=ZE-441199&tin=100022119&inv=ZESA-8001
""",
}


@router.get("/demo-fixtures")
def get_demo_fixtures() -> Dict[str, Any]:
    """Retrieve pre-packaged realistic Zimbabwean scanned invoice fixtures."""
    return {
        "fixtures": list(DEMO_SCANNED_INVOICES.keys()),
        "descriptions": {
            "delta_beverages": "Delta Beverages tax invoice (USD $1,155.00) with Fiscal Device FP-ZW-88902 billed to Delta Corporation (TIN 200012345)",
            "national_foods": "National Foods grain supply invoice (USD $2,887.50) with Fiscal Device NF-FDMS-302 billed to National Foods Holdings (TIN 200033889)",
            "econet_telecom": "Econet Wireless telecommunications invoice (USD $577.50) with Fiscal Device EW-SVR-0199 billed to Delta Corporation (TIN 200012345)",
            "zesa_electricity": "ZESA industrial power invoice (ZWG 17,325.00) segregated currency with Fiscal Device ZETDC-SVR-77 billed to Olivine Industries (TIN 200055778)",
        },
    }


@router.post("/recognize", response_model=RecognizeDocumentResponse)
def recognize_document_entities(
    payload: Optional[RecognizeDocumentRequest] = None,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecognizeDocumentResponse:
    """
    Intelligently parse scanned invoice text or template to auto-detect the
    Buyer / Taxpayer Company, Supplier, Zimbabwean TIN, VAT Category, and Amounts,
    and perform instant real-time statutory & fiscal verification.
    """
    raw_text = ""
    if payload and payload.preset_name and payload.preset_name in DEMO_SCANNED_INVOICES:
        raw_text = DEMO_SCANNED_INVOICES[payload.preset_name]
    elif payload and payload.raw_text:
        raw_text = payload.raw_text
    else:
        raw_text = DEMO_SCANNED_INVOICES["delta_beverages"]

    extracted = extract_entities_from_document_text(raw_text)
    resolution = resolve_or_propose_client(
        db=db,
        tenant_id=current_user.tenant_id,
        extracted_data=extracted,
    )
    realtime_validation = evaluate_statutory_and_fiscal_validity(
        db=db,
        tenant_id=current_user.tenant_id,
        extracted_data=extracted,
    )

    return RecognizeDocumentResponse(
        buyer_name=extracted["buyer_name"],
        buyer_tin=extracted["buyer_tin"],
        buyer_vat_number=extracted.get("buyer_vat_number"),
        supplier_name=extracted["supplier_name"],
        supplier_tin=extracted["supplier_tin"],
        invoice_number=extracted["invoice_number"],
        invoice_date=extracted["invoice_date"],
        currency=extracted["currency"],
        city=extracted["city"],
        net_amount=extracted["net_amount"],
        vat_amount=extracted["vat_amount"],
        gross_amount=extracted["gross_amount"],
        confidence_score=extracted["confidence_score"],
        resolution=resolution,
        fiscal_details=extracted.get("fiscal_details", {}),
        realtime_validation=realtime_validation,
        zimra_portal_url=realtime_validation.get("zimra_portal_url", extracted.get("zimra_portal_url", "https://fdms.zimra.co.zw/verify")),
    )


@router.post("/recognize-file", response_model=RecognizeDocumentResponse)
async def recognize_uploaded_file(
    file: UploadFile = File(...),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecognizeDocumentResponse:
    """
    Upload a real PDF or text file to intelligently extract company details and validate in real-time.
    """
    contents = await file.read()
    if file.filename and file.filename.lower().endswith(".pdf"):
        raw_text = extract_text_from_pdf_bytes(contents)
    else:
        try:
            raw_text = contents.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = contents.decode("latin-1", errors="ignore")

    extracted = extract_entities_from_document_text(raw_text)
    resolution = resolve_or_propose_client(
        db=db,
        tenant_id=current_user.tenant_id,
        extracted_data=extracted,
    )
    realtime_validation = evaluate_statutory_and_fiscal_validity(
        db=db,
        tenant_id=current_user.tenant_id,
        extracted_data=extracted,
    )

    return RecognizeDocumentResponse(
        buyer_name=extracted["buyer_name"],
        buyer_tin=extracted["buyer_tin"],
        buyer_vat_number=extracted.get("buyer_vat_number"),
        supplier_name=extracted["supplier_name"],
        supplier_tin=extracted["supplier_tin"],
        invoice_number=extracted["invoice_number"],
        invoice_date=extracted["invoice_date"],
        currency=extracted["currency"],
        city=extracted["city"],
        net_amount=extracted["net_amount"],
        vat_amount=extracted["vat_amount"],
        gross_amount=extracted["gross_amount"],
        confidence_score=extracted["confidence_score"],
        resolution=resolution,
        fiscal_details=extracted.get("fiscal_details", {}),
        realtime_validation=realtime_validation,
        zimra_portal_url=realtime_validation.get("zimra_portal_url", extracted.get("zimra_portal_url", "https://fdms.zimra.co.zw/verify")),
    )


@router.post("/auto-onboard", response_model=EngagementSummary)
def auto_onboard_recognized_company(
    payload: AutoOnboardRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EngagementSummary:
    """
    Zero-Friction Onboarding: Automatically creates or matches the taxpayer Client,
    creates a Reconciliation Engagement, and readies the system for immediate matching!
    """
    norm_tin = payload.buyer_tin.strip()

    # 1. Resolve or Create Client strictly within caller's tenant (HC-6)
    client = db.execute(
        select(Client).where(
            Client.tenant_id == current_user.tenant_id,
            Client.tin_normalised == norm_tin,
            Client.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if not client:
        client = Client(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            legal_name=payload.buyer_name.strip(),
            trading_name=payload.buyer_name.strip(),
            tin_raw=norm_tin,
            tin_normalised=norm_tin,
            vat_category=payload.vat_category,
            default_currency=payload.currency.upper(),
            city=payload.city or "Harare",
            contact_name="Accounts Payable Manager",
        )
        db.add(client)
        db.flush()

        log_audit_event(
            db=db,
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
            action="CLIENT_AUTO_RECOGNIZED_CREATED",
            entity_type="client",
            entity_id=str(client.id),
            after_json={"legal_name": client.legal_name, "tin": client.tin_normalised},
        )

    # 2. Create Engagement for this client
    ref = f"ENG-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:4].upper()}"
    p_start = date(2026, 1, 1)
    p_end = date(2026, 1, 31)

    eng = Engagement(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        client_id=client.id,
        reference=ref,
        period_start=p_start,
        period_end=p_end,
        currency=payload.currency.upper(),
        engagement_type=EngagementType.AUDIT,
        status=EngagementStatus.INGESTING,
        operator_id=current_user.id,
    )
    db.add(eng)
    db.flush()

    log_audit_event(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="ENGAGEMENT_AUTO_CREATED_FROM_SCAN",
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
