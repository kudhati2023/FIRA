from datetime import date
from fira.engine.normalisation import (
    normalise_tin, normalise_invoice_number, normalise_supplier_name,
    parse_amount_minor, normalise_currency, parse_date
)

def test_normalise_tin() -> None:
    assert normalise_tin("TIN: 200-123-456") == "200123456"
    assert normalise_tin("200 123 456") == "200123456"
    assert normalise_tin("ZW200123456A") == "200123456"
    assert normalise_tin(None) is None
    assert normalise_tin("") is None

def test_normalise_invoice_number() -> None:
    assert normalise_invoice_number("inv-000452") == "INV452"
    assert normalise_invoice_number("INV/2026/00012") == "INV202612"
    assert normalise_invoice_number("000987") == "987"
    assert normalise_invoice_number(" #INV-99-001 ") == "INV991"
    assert normalise_invoice_number("INV-0000") == "INV0"

def test_normalise_supplier_name() -> None:
    full, stripped = normalise_supplier_name("Chikwanha Hardware (Pvt) Ltd")
    assert full == "CHIKWANHA HARDWARE PVT LTD"
    assert stripped == "CHIKWANHA HARDWARE"

    full, stripped = normalise_supplier_name("Econet Wireless Zimbabwe Limited")
    assert full == "ECONET WIRELESS ZIMBABWE LIMITED"
    assert stripped == "ECONET WIRELESS ZIMBABWE"

def test_parse_amount_minor() -> None:
    assert parse_amount_minor(1234.50) == (123450, True)
    assert parse_amount_minor("$1,234.50") == (123450, True)
    assert parse_amount_minor("(1,234.50)") == (-123450, True)
    assert parse_amount_minor("1,234.50 CR") == (-123450, True)
    assert parse_amount_minor("1,234.50 DR") == (123450, True)
    assert parse_amount_minor("-500.25") == (-50025, True)
    assert parse_amount_minor("US$ 10,000.00") == (1000000, True)
    assert parse_amount_minor("invalid")[1] is False

def test_normalise_currency() -> None:
    assert normalise_currency("US$") == "USD"
    assert normalise_currency("$") == "USD"
    assert normalise_currency("ZiG") == "ZWG"
    assert normalise_currency("ZWL") == "ZWG"
    assert normalise_currency(None, default="USD") == "USD"

def test_parse_date() -> None:
    # Zimbabwe convention: DD/MM/YYYY
    d, ok = parse_date("01/02/2026")
    assert ok is True
    assert d == date(2026, 2, 1)

    d, ok = parse_date("2026-03-15")
    assert ok is True
    assert d == date(2026, 3, 15)

    d, ok = parse_date("15-Jan-2026")
    assert ok is True
    assert d == date(2026, 1, 15)
