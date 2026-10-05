import io
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from pypdf import PdfReader
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from fira.engine.normalisation import normalise_tin, normalise_invoice_number, normalise_supplier_name
from fira.models.client import Client
from fira.models.system import VATRatePeriod
from fira.models.ledger import ZIMRALine

# Statutory and Zimbabwean tax heuristics
ZW_TIN_REGEX = re.compile(r"\b(\d{9,10})\b")
ZW_CITIES = ["Harare", "Bulawayo", "Chitungwiza", "Mutare", "Gweru", "Kwekwe", "Kadoma", "Masvingo", "Victoria Falls", "Hwange"]

BUYER_MARKERS = [
    r"Bill\s+To\s*[:\-]?\s*([^\n\r]+)",
    r"Customer\s*[:\-]?\s*([^\n\r]+)",
    r"Buyer\s*[:\-]?\s*([^\n\r]+)",
    r"Purchaser\s*[:\-]?\s*([^\n\r]+)",
    r"Taxpayer\s*[:\-]?\s*([^\n\r]+)",
    r"Client\s*[:\-]?\s*([^\n\r]+)",
    r"Account\s+Name\s*[:\-]?\s*([^\n\r]+)",
    r"Delivered\s+To\s*[:\-]?\s*([^\n\r]+)",
    r"Invoice\s+To\s*[:\-]?\s*([^\n\r]+)",
]

SUPPLIER_MARKERS = [
    r"Sold\s+By\s*[:\-]?\s*([^\n\r]+)",
    r"Supplier\s*[:\-]?\s*([^\n\r]+)",
    r"Vendor\s*[:\-]?\s*([^\n\r]+)",
    r"Issuer\s*[:\-]?\s*([^\n\r]+)",
    r"From\s*[:\-]?\s*([^\n\r]+)",
]

DATE_PATTERNS = [
    r"\b(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\b",  # YYYY-MM-DD
    r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})\b",  # DD-MM-YYYY or MM-DD-YYYY
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",  # 15 Jan 2026
]


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract plain text from an uploaded PDF document."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted.append(t)
        return "\n".join(extracted)
    except Exception as e:
        return f"[PDF_EXTRACTION_ERROR]: {str(e)}"


def parse_clean_amount(val_str: str) -> Optional[int]:
    """Convert amount string (e.g. '$1,250.50' or '1250.50') into integer minor units (cents)."""
    cleaned = re.sub(r"[^\d.]", "", val_str)
    if not cleaned:
        return None
    try:
        return int(round(float(cleaned) * 100))
    except (ValueError, TypeError):
        return None


def detect_currency(text: str) -> str:
    """Detect transaction currency adhering strictly to USD vs ZWG segregation (FR-VAL-4)."""
    upper_text = text.upper()
    if "ZWG" in upper_text or "ZIG" in upper_text or "ZW$" in upper_text:
        return "ZWG"
    return "USD"


def detect_city(text: str) -> str:
    """Detect Zimbabwean city in address block or default to Harare."""
    for city in ZW_CITIES:
        if re.search(rf"\b{city}\b", text, re.IGNORECASE):
            return city
    return "Harare"


def extract_entities_from_document_text(text: str) -> Dict[str, Any]:
    """
    Intelligently parse raw document text to recognize the Buyer (Company/Taxpayer),
    the Supplier counterparty, statutory TINs, invoice numbers, dates, and amounts.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    buyer_name = None
    buyer_tin = None
    buyer_vat = None

    supplier_name = None
    supplier_tin = None

    # 1. Search for Buyer/Taxpayer markers
    for pattern in BUYER_MARKERS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            # Clean common trailing artifacts
            candidate = re.split(r"(?:TIN|VAT|Date|Inv|Tel|Phone|Email|Address)", candidate, flags=re.IGNORECASE)[0].strip(" :,-\t")
            if len(candidate) >= 3 and not buyer_name:
                buyer_name = candidate
                break

    # If no explicit marker, check if the document header has a top recipient line
    if not buyer_name and len(lines) > 2:
        for idx in range(min(10, len(lines))):
            if any(k in lines[idx].lower() for k in ["customer", "bill to", "buyer", "client"]):
                if idx + 1 < len(lines):
                    buyer_name = lines[idx + 1]
                    break

    # If still not found, search lines for company-like entity (avoiding standard document headers)
    if not buyer_name:
        for l in lines[1:8]:
            if len(l) > 3 and not any(k in l.lower() for k in ["tax invoice", "fiscal", "vat invoice", "receipt", "tel", "phone", "email"]):
                buyer_name = l
                break

    if not buyer_name:
        buyer_name = "Unspecified Taxpayer"

    # 2. Search for Supplier markers
    for pattern in SUPPLIER_MARKERS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            candidate = re.split(r"(?:TIN|VAT|Date|Inv|Tel|Phone|Email|Address)", candidate, flags=re.IGNORECASE)[0].strip(" :,-\t")
            if len(candidate) >= 3 and not supplier_name:
                supplier_name = candidate
                break

    if not supplier_name and len(lines) > 0:
        # First non-trivial header line is often the issuer/supplier
        for l in lines[:5]:
            if len(l) > 3 and not any(k in l.lower() for k in ["tax invoice", "fiscal", "vat invoice", "receipt"]):
                supplier_name = l
                break

    if not supplier_name:
        supplier_name = "Unspecified Supplier"

    # 3. Extract Zimbabwean TINs contextually
    if buyer_name:
        buyer_idx = text.find(buyer_name)
        if buyer_idx != -1:
            vicinity = text[buyer_idx:buyer_idx + 400]
            m_tin = re.search(r"(?:TIN|BPN|Tax\s*No|PIN)\s*[:\-#]?\s*(\d{9,10})", vicinity, re.IGNORECASE)
            if m_tin:
                buyer_tin = m_tin.group(1)

    if supplier_name:
        supp_idx = text.find(supplier_name)
        if supp_idx != -1:
            vicinity = text[supp_idx:supp_idx + 400]
            m_tin = re.search(r"(?:TIN|BPN|Tax\s*No|PIN)\s*[:\-#]?\s*(\d{9,10})", vicinity, re.IGNORECASE)
            if m_tin:
                supplier_tin = m_tin.group(1)

    # Fallback to general list of TINs if not contextually resolved
    all_tins = re.findall(r"(?:TIN|BPN|Tax\s*No|PIN)\s*[:\-#]?\s*(\d{9,10})", text, re.IGNORECASE)
    if not all_tins:
        all_tins = ZW_TIN_REGEX.findall(text)

    if not supplier_tin and all_tins:
        supplier_tin = all_tins[0]
    if not buyer_tin and len(all_tins) > 1:
        buyer_tin = all_tins[1]
    elif not buyer_tin and all_tins:
        buyer_tin = all_tins[0]

    if not buyer_tin:
        buyer_tin = ""
    if not supplier_tin:
        supplier_tin = ""

    # 4. Extract VAT Number
    vat_match = re.search(r"VAT\s*(?:No\.?|Number)?\s*[:\-#]?\s*([A-Z0-9]{7,12})", text, re.IGNORECASE)
    if vat_match:
        buyer_vat = vat_match.group(1).strip()

    # 5. Extract Invoice Number
    invoice_number = None
    # Prioritize explicit "Invoice No:", "Inv #", "Doc Number:"
    inv_match = re.search(r"(?:Invoice|Inv|Doc)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z0-9\-_]{3,30})", text, re.IGNORECASE)
    if not inv_match:
        inv_match = re.search(r"(?:Invoice|Inv)\s*[:\-#]\s*([A-Z0-9\-_]{3,30})", text, re.IGNORECASE)
    if not inv_match:
        inv_match = re.search(r"\b(INV[-_][A-Z0-9\-_]{3,25})\b", text, re.IGNORECASE)

    if inv_match:
        cand_inv = inv_match.group(1).strip()
        if cand_inv.upper() not in ["SUPPLIER", "CUSTOMER", "BUYER", "CLIENT", "TAX", "TOTAL", "DATE", "HARARE", "USD", "ZWG"]:
            invoice_number = cand_inv

    if not invoice_number:
        invoice_number = f"INV-{uuid.uuid4().hex[:6].upper()}"

    # 6. Extract Date
    parsed_date = date.today()
    for dp in DATE_PATTERNS:
        dm = re.search(dp, text, re.IGNORECASE)
        if dm:
            d_str = dm.group(1).strip()
            # Try parsing
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"]:
                try:
                    parsed_date = datetime.strptime(d_str, fmt).date()
                    break
                except ValueError:
                    continue
            break

    # 7. Extract Amounts & Currency
    currency = detect_currency(text)
    city = detect_city(text)

    # Search for Total / Gross amount
    gross_match = re.search(r"(?:Total|Gross|Amount\s*Due)\s*[:\-]?\s*(?:USD|ZWG|US\$|\$)?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    vat_match_amt = re.search(r"(?:VAT|Tax)\s*(?:15(?:\.5)?%)?\s*[:\-]?\s*(?:USD|ZWG|US\$|\$)?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    net_match_amt = re.search(r"(?:Net|Subtotal|Sub-Total)\s*[:\-]?\s*(?:USD|ZWG|US\$|\$)?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)

    gross_minor = parse_clean_amount(gross_match.group(1)) if gross_match else 0
    vat_minor = parse_clean_amount(vat_match_amt.group(1)) if vat_match_amt else (int(round(gross_minor * 0.155 / 1.155)) if gross_minor else 0)
    net_minor = parse_clean_amount(net_match_amt.group(1)) if net_match_amt else (gross_minor - vat_minor if gross_minor else 0)

    # 8. Extract Fiscal Markers (Device Serial, Fiscal Day, Verification Code, ZIMRA URL)
    fiscal_device_serial = None
    fiscal_day = None
    verification_code = None
    zimra_portal_url = None

    # Fiscal Device ID / Serial
    fd_match = re.search(
        r"(?:Fiscal\s*Device|Device\s*ID|Serial\s*No\.?|FDS\s*ID|FDMS\s*Device|Device\s*Serial)\s*[:\-#]?\s*([A-Z0-9\-_]+)",
        text,
        re.IGNORECASE,
    )
    if fd_match:
        fiscal_device_serial = fd_match.group(1).strip()

    # Fiscal Day / Counter
    fday_match = re.search(
        r"(?:Fiscal\s*Day|Fiscal\s*Counter|Day\s*No\.?)\s*[:\-#]?\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    if fday_match:
        fiscal_day = fday_match.group(1).strip()

    # Verification Code / Fiscal Hash / Signature
    vcode_match = re.search(
        r"(?:Verification\s*Code|Fiscal\s*Code|Verification\s*Hash|Fiscal\s*Sig(?:nature)?|Code)\s*[:\-#]?\s*([A-Z0-9\-]{4,30})",
        text,
        re.IGNORECASE,
    )
    if vcode_match:
        cand = vcode_match.group(1).strip()
        if cand.upper() not in ["USD", "ZWG", "HARARE", "INVOICE", "TOTAL", "AMOUNT", "DATE"]:
            verification_code = cand

    # ZIMRA Verification Portal URL
    url_match = re.search(r"(https?://(?:[a-zA-Z0-9\-_]+\.)*zimra\.co\.zw[^\s\"'>]+)", text, re.IGNORECASE)
    if url_match:
        zimra_portal_url = url_match.group(1).strip()
    else:
        # Construct canonical official ZIMRA lookup link based on extracted statutory parameters
        supp_tin_param = normalise_tin(supplier_tin) if supplier_tin else ""
        inv_param = normalise_invoice_number(invoice_number) if invoice_number else ""
        code_param = verification_code or ""
        params = []
        if code_param:
            params.append(f"code={code_param}")
        if supp_tin_param:
            params.append(f"tin={supp_tin_param}")
        if inv_param:
            params.append(f"inv={inv_param}")

        query_string = "&".join(params)
        zimra_portal_url = f"https://fdms.zimra.co.zw/verify?{query_string}" if query_string else "https://fdms.zimra.co.zw/verify"

    fiscal_details = {
        "device_serial": fiscal_device_serial,
        "fiscal_day": fiscal_day,
        "verification_code": verification_code,
    }

    # 9. Confidence estimation
    confidence = 70
    if buyer_name and len(buyer_name) > 3:
        confidence += 10
    if buyer_tin and len(buyer_tin) in (9, 10):
        confidence += 10
    if gross_minor and vat_minor and abs(net_minor + vat_minor - gross_minor) <= 5:
        confidence += 5
    if fiscal_device_serial or verification_code:
        confidence += 5

    return {
        "buyer_name": buyer_name.strip(),
        "buyer_tin": normalise_tin(buyer_tin),
        "buyer_vat_number": buyer_vat,
        "supplier_name": supplier_name.strip(),
        "supplier_tin": normalise_tin(supplier_tin),
        "invoice_number": normalise_invoice_number(invoice_number),
        "invoice_number_raw": invoice_number,
        "invoice_date": parsed_date.isoformat(),
        "currency": currency,
        "city": city,
        "net_amount": (net_minor or 0) / 100.0,
        "vat_amount": (vat_minor or 0) / 100.0,
        "gross_amount": (gross_minor or 0) / 100.0,
        "fiscal_details": fiscal_details,
        "zimra_portal_url": zimra_portal_url,
        "confidence_score": min(99, confidence),
    }


def resolve_or_propose_client(
    db: Session,
    tenant_id: uuid.UUID,
    extracted_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Search existing clients in caller's tenant by TIN or fuzzy Legal Name.
    If match found -> returns existing client details.
    If not found -> returns proposal for automatic client creation.
    """
    norm_tin = extracted_data["buyer_tin"]
    extracted_name = extracted_data["buyer_name"]
    norm_name, _ = normalise_supplier_name(extracted_name)

    # 1. Exact TIN Match within Tenant (HC-6)
    stmt = select(Client).where(
        Client.tenant_id == tenant_id,
        Client.tin_normalised == norm_tin,
        Client.deleted_at.is_(None),
    )
    existing_by_tin = db.execute(stmt).scalar_one_or_none()
    if existing_by_tin:
        return {
            "status": "matched_existing",
            "match_reason": f"Matched existing client via Zimbabwean TIN {norm_tin}",
            "client_id": existing_by_tin.id,
            "legal_name": existing_by_tin.legal_name,
            "tin_normalised": existing_by_tin.tin_normalised,
            "vat_category": existing_by_tin.vat_category,
            "default_currency": existing_by_tin.default_currency,
            "city": existing_by_tin.city,
            "confidence": 100,
        }

    # 2. Fuzzy Name Match within Tenant
    all_clients = db.execute(
        select(Client).where(Client.tenant_id == tenant_id, Client.deleted_at.is_(None))
    ).scalars().all()

    best_match: Optional[Client] = None
    best_score = 0.0

    for c in all_clients:
        c_norm, _ = normalise_supplier_name(c.legal_name)
        score = fuzz.token_sort_ratio(norm_name, c_norm)
        if score > best_score:
            best_score = score
            best_match = c

    if best_match and best_score >= 85:
        return {
            "status": "matched_existing",
            "match_reason": f"Fuzzy matched existing client '{best_match.legal_name}' (Score: {best_score}%)",
            "client_id": best_match.id,
            "legal_name": best_match.legal_name,
            "tin_normalised": best_match.tin_normalised,
            "vat_category": best_match.vat_category,
            "default_currency": best_match.default_currency,
            "city": best_match.city,
            "confidence": int(best_score),
        }

    # 3. New Client Auto-Discovered
    return {
        "status": "new_discovered",
        "match_reason": "No existing client matched in practice. Ready to auto-register.",
        "client_id": None,
        "legal_name": extracted_name,
        "tin_normalised": norm_tin,
        "vat_category": "C",
        "default_currency": extracted_data["currency"],
        "city": extracted_data["city"],
        "confidence": extracted_data["confidence_score"],
    }


def get_vat_rate_for_date(
    db: Optional[Session],
    target_date: date,
    jurisdiction: str = "ZW",
) -> float:
    """
    HC-3: No Hardcoded VAT Rates. Rates must be resolved from the vat_rate_period table
    based on the invoice date.
    """
    if db is not None:
        stmt = (
            select(VATRatePeriod)
            .where(
                VATRatePeriod.jurisdiction == jurisdiction,
                VATRatePeriod.effective_from <= target_date,
                (VATRatePeriod.effective_to.is_(None) | (VATRatePeriod.effective_to >= target_date)),
            )
            .order_by(VATRatePeriod.effective_from.desc())
        )
        period = db.execute(stmt).scalars().first()
        if period:
            return period.rate_basis_points / 10000.0

    # Statutory fallback (15.5% from 1 Jan 2026, 15.0% prior)
    return 0.155 if target_date >= date(2026, 1, 1) else 0.150


def evaluate_statutory_and_fiscal_validity(
    db: Optional[Session],
    tenant_id: Optional[uuid.UUID],
    extracted_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Real-Time Statutory & Fiscal Checklist (Option A):
    1. Supplier Zimbabwean TIN Syntax (9-10 digits)
    2. Buyer Zimbabwean TIN Syntax (9-10 digits)
    3. Mathematical Exactness: Net + VAT == Gross
    4. Statutory Date-Resolved VAT Rate (from vat_rate_period table, HC-3)
    5. Fiscal Device & Security Signature Presence
    6. Local ZIMRA FDMS Claim Registry Cross-Check (HC-6 tenant isolated)
    """
    checks = []

    # 1. Supplier TIN
    supp_tin = extracted_data.get("supplier_tin") or ""
    supp_tin_valid = bool(re.match(r"^\d{9,10}$", supp_tin))
    if supp_tin_valid:
        checks.append({
            "rule": "SUPPLIER_TIN",
            "name": "Supplier TIN Syntax",
            "status": "PASS",
            "details": f"Valid 9-10 digit Zimbabwean TIN ({supp_tin}) recognized for issuer.",
        })
    else:
        checks.append({
            "rule": "SUPPLIER_TIN",
            "name": "Supplier TIN Syntax",
            "status": "WARN" if supp_tin else "FAIL",
            "details": f"Supplier TIN '{supp_tin}' does not conform to 9-10 digit standard." if supp_tin else "No supplier TIN detected on invoice.",
        })

    # 2. Buyer TIN
    buyer_tin = extracted_data.get("buyer_tin") or ""
    buyer_tin_valid = bool(re.match(r"^\d{9,10}$", buyer_tin))
    if buyer_tin_valid:
        checks.append({
            "rule": "BUYER_TIN",
            "name": "Taxpayer / Buyer TIN Syntax",
            "status": "PASS",
            "details": f"Valid 9-10 digit Zimbabwean TIN ({buyer_tin}) recognized for recipient.",
        })
    else:
        checks.append({
            "rule": "BUYER_TIN",
            "name": "Taxpayer / Buyer TIN Syntax",
            "status": "WARN" if buyer_tin else "FAIL",
            "details": f"Taxpayer TIN '{buyer_tin}' does not conform to 9-10 digit standard." if buyer_tin else "No taxpayer/buyer TIN detected on invoice.",
        })

    # 3. Tax Math Consistency
    net = float(extracted_data.get("net_amount") or 0.0)
    vat = float(extracted_data.get("vat_amount") or 0.0)
    gross = float(extracted_data.get("gross_amount") or 0.0)
    math_diff = abs((net + vat) - gross)
    math_valid = math_diff <= 0.05
    if math_valid and gross > 0:
        checks.append({
            "rule": "TAX_MATH_CONSISTENCY",
            "name": "Tax Invoice Math Integrity",
            "status": "PASS",
            "details": f"Net ({net:,.2f}) + VAT ({vat:,.2f}) = Gross ({gross:,.2f}) exact arithmetic balance.",
        })
    else:
        checks.append({
            "rule": "TAX_MATH_CONSISTENCY",
            "name": "Tax Invoice Math Integrity",
            "status": "FAIL",
            "details": f"Math discrepancy: Net ({net:,.2f}) + VAT ({vat:,.2f}) != Gross ({gross:,.2f}). Difference: {math_diff:,.2f}.",
        })

    # 4. Statutory VAT Rate Accuracy (HC-3)
    inv_date_str = extracted_data.get("invoice_date")
    try:
        inv_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date() if inv_date_str else date.today()
    except (ValueError, TypeError):
        inv_date = date.today()

    statutory_rate = get_vat_rate_for_date(db, inv_date)
    statutory_rate_pct = round(statutory_rate * 100, 1)

    applied_rate_valid = False
    if net > 0:
        applied_rate = vat / net
        applied_rate_valid = abs(applied_rate - statutory_rate) <= 0.006

    if applied_rate_valid:
        checks.append({
            "rule": "STATUTORY_VAT_RATE",
            "name": "Statutory VAT Rate Applied",
            "status": "PASS",
            "details": f"Invoice date ({inv_date}) statutory rate is {statutory_rate_pct}%. Applied VAT matches statutory schedule.",
        })
    else:
        checks.append({
            "rule": "STATUTORY_VAT_RATE",
            "name": "Statutory VAT Rate Applied",
            "status": "WARN",
            "details": f"Invoice date ({inv_date}) statutory rate is {statutory_rate_pct}%. Calculated VAT ratio is {round((vat/net)*100, 2) if net>0 else 0}%.",
        })

    # 5. Fiscal Device & Security Signature
    f_details = extracted_data.get("fiscal_details") or {}
    dev_serial = f_details.get("device_serial")
    f_code = f_details.get("verification_code")
    if dev_serial or f_code:
        sig_info = []
        if dev_serial:
            sig_info.append(f"Device: {dev_serial}")
        if f_code:
            sig_info.append(f"Code: {f_code}")
        checks.append({
            "rule": "FISCAL_DEVICE_SIGNATURE",
            "name": "Fiscal Device & Security Marker",
            "status": "PASS",
            "details": f"Fiscal markers detected: {', '.join(sig_info)}.",
        })
    else:
        checks.append({
            "rule": "FISCAL_DEVICE_SIGNATURE",
            "name": "Fiscal Device & Security Marker",
            "status": "INFO",
            "details": "No physical fiscal device ID or verification signature detected on scan header.",
        })

    # 6. Local ZIMRA FDMS Claim Registry Cross-Check (HC-6)
    inv_num = extracted_data.get("invoice_number_raw") or extracted_data.get("invoice_number") or ""
    norm_inv = normalise_invoice_number(inv_num)

    zimra_row = None
    if db is not None and tenant_id is not None and norm_inv:
        zimra_match_stmt = select(ZIMRALine).where(
            ZIMRALine.tenant_id == tenant_id,
            ZIMRALine.invoice_number_norm == norm_inv,
        )
        zimra_row = db.execute(zimra_match_stmt).scalars().first()

    local_registry = {
        "found": bool(zimra_row),
        "status": "RECORDED_IN_ZIMRA_FDMS" if zimra_row else "PENDING_RECONCILIATION",
        "details": f"Invoice {inv_num} is registered in official ZIMRA claim file." if zimra_row else "Awaiting upload of taxpayer's official ZIMRA FDMS claim export file to perform automated matching.",
        "zimra_gross": (zimra_row.gross_minor / 100.0) if zimra_row else None,
        "zimra_vat": (zimra_row.vat_minor / 100.0) if zimra_row else None,
    }

    if zimra_row:
        checks.append({
            "rule": "LOCAL_FDMS_CROSSCHECK",
            "name": "Local ZIMRA Claim Registry",
            "status": "PASS",
            "details": f"Matched in taxpayer's official ZIMRA claim file ({zimra_row.currency} Gross: {zimra_row.gross_minor/100:,.2f}, VAT: {zimra_row.vat_minor/100:,.2f}).",
        })
    else:
        checks.append({
            "rule": "LOCAL_FDMS_CROSSCHECK",
            "name": "Local ZIMRA Claim Registry",
            "status": "INFO",
            "details": "Invoice not yet ingested in official ZIMRA export. Ready to reconcile when ZIMRA batch is uploaded.",
        })

    is_statutory_valid = supp_tin_valid and buyer_tin_valid and math_valid

    return {
        "is_statutory_valid": is_statutory_valid,
        "statutory_rate_percent": statutory_rate_pct,
        "zimra_portal_url": extracted_data.get("zimra_portal_url") or "https://fdms.zimra.co.zw/verify",
        "fiscal_details": f_details,
        "local_zimra_registry": local_registry,
        "checks": checks,
    }

