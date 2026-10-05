import io
from datetime import date
import pytest
from fira.engine.file_ingestion import parse_ap_ledger_file, parse_zimra_claim_file


SAMPLE_AP_CSV = """Supplier Name,TIN,Invoice No,Invoice Date,Net,VAT,Gross,Currency,Expense Category
Delta Beverages Limited,100012345,INV-DB-9081,2026-01-10,1000.00,155.00,1155.00,USD,Inventory
Econet Wireless Zimbabwe,100098765,EC-8801,2026-01-12,500.00,77.50,577.50,USD,Telecommunications
National Foods Ltd,100033445,NF-2026-104,2026-01-15,2500.00,387.50,2887.50,USD,Raw Materials
ZETDC Power,100022119,ZESA-8001,2026-01-28,15000.00,2325.00,17325.00,ZWG,Utilities
"""

SAMPLE_ZIMRA_CSV = """Taxpayer Name,Supplier TIN,Fiscal Invoice Number,Fiscal Date,Net Amount,VAT Amount,Gross Amount,Currency,Customer Name,Customer TIN,Status
Delta Beverages Limited,100012345,INV-DB-9081,2026-01-10,1000.00,155.00,1155.00,USD,Delta Corporation Limited,200012345,VALID
Econet Wireless Zimbabwe,100098765,EC8801,2026-01-12,500.00,77.50,577.50,USD,Delta Corporation Limited,200012345,VALID
Chiredzi Hardware Supplies,100099112,CH-1002,2026-01-29,600.00,93.00,693.00,USD,Delta Corporation Limited,200012345,CANCELLED_INVALID
"""


def test_parse_ap_ledger_csv():
    stream = io.BytesIO(SAMPLE_AP_CSV.encode("utf-8"))
    lines = parse_ap_ledger_file(stream, ext=".csv", default_currency="USD")

    assert len(lines) == 4

    # Check Line 1 (Delta)
    line1 = lines[0]
    assert line1["supplier_name_raw"] == "Delta Beverages Limited"
    assert line1["supplier_tin_norm"] == "100012345"
    assert line1["invoice_number_norm"] == "INVDB9081"
    assert line1["invoice_date"] == date(2026, 1, 10)
    assert line1["currency"] == "USD"
    assert line1["net_minor"] == 100000
    assert line1["vat_minor"] == 15500
    assert line1["gross_minor"] == 115500

    # Check Line 4 (ZETDC ZWG)
    line4 = lines[3]
    assert line4["currency"] == "ZWG"
    assert line4["gross_minor"] == 1732500
    assert line4["vat_minor"] == 232500


def test_parse_zimra_claim_csv():
    stream = io.BytesIO(SAMPLE_ZIMRA_CSV.encode("utf-8"))
    lines = parse_zimra_claim_file(stream, ext=".csv", default_currency="USD")

    assert len(lines) == 3

    line1 = lines[0]
    assert line1["supplier_name_raw"] == "Delta Beverages Limited"
    assert line1["supplier_tin_norm"] == "100012345"
    assert line1["validity_is_valid"] is True
    assert line1["validity_status_raw"] == "VALID"

    # Line 3 is cancelled / invalid in ZIMRA fiscal system
    line3 = lines[2]
    assert line3["validity_is_valid"] is False
    assert line3["validity_status_raw"] == "CANCELLED_INVALID"


def test_parse_ap_ledger_with_missing_vat_calculates_statutory():
    csv_missing_vat = """Supplier,Invoice,Date,Total
Supplier Alpha,INV-001,2026-01-10,1155.00
"""
    stream = io.BytesIO(csv_missing_vat.encode("utf-8"))
    lines = parse_ap_ledger_file(stream, ext=".csv", default_currency="USD")

    assert len(lines) == 1
    assert lines[0]["gross_minor"] == 115500
    # In 2026 statutory VAT is 15.5% -> 15500 cents
    assert lines[0]["vat_minor"] == 15500
    assert lines[0]["net_minor"] == 100000
