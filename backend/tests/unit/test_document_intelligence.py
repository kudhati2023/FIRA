import pytest
from datetime import date
from fira.engine.document_intelligence import (
    extract_entities_from_document_text,
    detect_currency,
    detect_city,
    parse_clean_amount,
)

SAMPLE_INVOICE_TEXT = """
TAX INVOICE — FISCAL RECIPIENT
Delta Beverages Limited
Sutherland Road, Workington, Harare, Zimbabwe
TIN: 100012345 | VAT No: 10023456

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
"""

SAMPLE_ZWG_INVOICE = """
ZIMBABWE ELECTRICITY TRANSMISSION & DISTRIBUTION CO (ZETDC)
TAX INVOICE
TIN: 100022119 | VAT No: 10099887

DATE: 28 January 2026
INVOICE NO: ZESA-8001

CUSTOMER:
Olivine Industries (Pvt) Ltd
Birmingham Road, Southerton, Harare
TIN: 200055778

Description: Maximum Demand Industrial Power Supply
Net Amount: ZWG 15,000.00
VAT (15.5%): ZWG 2,325.00
GROSS TOTAL: ZWG 17,325.00
"""

def test_extract_entities_usd_invoice():
    extracted = extract_entities_from_document_text(SAMPLE_INVOICE_TEXT)
    
    assert "Delta Corporation" in extracted["buyer_name"]
    assert extracted["buyer_tin"] == "200012345"
    assert "Delta Beverages" in extracted["supplier_name"]
    assert extracted["currency"] == "USD"
    assert extracted["city"] == "Harare"
    assert extracted["gross_amount"] == 1155.00
    assert extracted["vat_amount"] == 155.00
    assert extracted["confidence_score"] >= 80

def test_extract_entities_zwg_invoice():
    extracted = extract_entities_from_document_text(SAMPLE_ZWG_INVOICE)
    
    assert "Olivine Industries" in extracted["buyer_name"]
    assert extracted["buyer_tin"] == "200055778"
    assert extracted["currency"] == "ZWG"
    assert extracted["gross_amount"] == 17325.00
    assert extracted["vat_amount"] == 2325.00

def test_detect_currency():
    assert detect_currency("Total Amount: USD 500.00") == "USD"
    assert detect_currency("Total Amount: ZWG 12,000.00") == "ZWG"
    assert detect_currency("Total: ZiG 450.00") == "ZWG"

def test_detect_city():
    assert detect_city("12 Fort Street, Bulawayo, Zimbabwe") == "Bulawayo"
    assert detect_city("Main Street, Mutare") == "Mutare"
    assert detect_city("No city mentioned") == "Harare"

def test_parse_clean_amount():
    assert parse_clean_amount("$1,250.50") == 125050
    assert parse_clean_amount("450.00") == 45000
    assert parse_clean_amount("invalid") is None


def test_extract_fiscal_markers():
    fiscal_invoice = """
    TAX INVOICE
    Supplier: Delta Beverages Limited
    TIN: 100012345
    Customer: Delta Corporation Limited
    TIN: 200012345
    Invoice No: INV-DB-9081
    Date: 2026-01-10
    Fiscal Device: FP-ZW-88902 | Fiscal Day: 42
    Verification Code: DB-998812
    Net: USD 1,000.00
    VAT: USD 155.00
    Total: USD 1,155.00
    ZIMRA Verification URL: https://fdms.zimra.co.zw/verify?code=DB-998812
    """
    extracted = extract_entities_from_document_text(fiscal_invoice)
    assert extracted["fiscal_details"]["device_serial"] == "FP-ZW-88902"
    assert extracted["fiscal_details"]["fiscal_day"] == "42"
    assert extracted["fiscal_details"]["verification_code"] == "DB-998812"
    assert "zimra.co.zw" in extracted["zimra_portal_url"]


def test_evaluate_statutory_and_fiscal_validity_success():
    from fira.engine.document_intelligence import evaluate_statutory_and_fiscal_validity

    extracted = {
        "supplier_tin": "100012345",
        "buyer_tin": "200012345",
        "net_amount": 1000.00,
        "vat_amount": 155.00,
        "gross_amount": 1155.00,
        "invoice_date": "2026-01-10",
        "invoice_number": "INV-100",
        "fiscal_details": {"device_serial": "FP-ZW-100", "verification_code": "VCODE-1"},
        "zimra_portal_url": "https://fdms.zimra.co.zw/verify?code=VCODE-1",
    }
    result = evaluate_statutory_and_fiscal_validity(db=None, tenant_id=None, extracted_data=extracted)

    assert result["is_statutory_valid"] is True
    assert result["statutory_rate_percent"] == 15.5
    assert len(result["checks"]) >= 5

    # All statutory checks should pass
    statuses = {c["rule"]: c["status"] for c in result["checks"]}
    assert statuses["SUPPLIER_TIN"] == "PASS"
    assert statuses["BUYER_TIN"] == "PASS"
    assert statuses["TAX_MATH_CONSISTENCY"] == "PASS"
    assert statuses["STATUTORY_VAT_RATE"] == "PASS"
    assert statuses["FISCAL_DEVICE_SIGNATURE"] == "PASS"


def test_evaluate_statutory_and_fiscal_validity_math_discrepancy():
    from fira.engine.document_intelligence import evaluate_statutory_and_fiscal_validity

    # Net (1000) + VAT (155) != Gross (1200) -> 45 dollar math error
    extracted = {
        "supplier_tin": "100012345",
        "buyer_tin": "200012345",
        "net_amount": 1000.00,
        "vat_amount": 155.00,
        "gross_amount": 1200.00,
        "invoice_date": "2026-01-10",
        "invoice_number": "INV-ERR-01",
    }
    result = evaluate_statutory_and_fiscal_validity(db=None, tenant_id=None, extracted_data=extracted)

    assert result["is_statutory_valid"] is False
    statuses = {c["rule"]: c["status"] for c in result["checks"]}
    assert statuses["TAX_MATH_CONSISTENCY"] == "FAIL"


def test_statutory_vat_rate_resolution():
    from fira.engine.document_intelligence import get_vat_rate_for_date

    # 2025 date -> 15.0%
    assert get_vat_rate_for_date(None, date(2025, 6, 1)) == 0.150
    # 2026 date -> 15.5%
    assert get_vat_rate_for_date(None, date(2026, 1, 1)) == 0.155

