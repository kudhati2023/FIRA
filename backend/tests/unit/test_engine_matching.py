from datetime import date
from fira.engine.types import (
    NormalisedLine, DocumentType, ClientParticulars,
    ExceptionClass, MatchConfig, ManualDecision
)
from fira.engine.reconciler import reconcile

CLIENT = ClientParticulars(
    client_id="client-001",
    legal_name_norm="ACME HOLDINGS ZIMBABWE",
    trading_name_norm="ACME STORES",
    tin_normalised="200112233",
    vat_number="VAT-998877"
)

def make_ap_line(line_id: str, tin: str, inv: str, dt: date, net: int, vat: int, curr: str = "USD", name: str = "DELTA BEVERAGES") -> NormalisedLine:
    return NormalisedLine(
        line_id=line_id,
        source_row_number=1,
        supplier_name_raw=name,
        supplier_name_norm=name,
        supplier_name_stripped=name,
        supplier_tin_raw=tin,
        supplier_tin_norm=tin,
        invoice_number_raw=inv,
        invoice_number_norm=inv,
        invoice_date=dt,
        document_type=DocumentType.INVOICE,
        currency=curr,
        net_minor=net,
        vat_minor=vat,
        gross_minor=net + vat
    )

def make_zimra_line(line_id: str, tin: str, inv: str, dt: date, net: int, vat: int, curr: str = "USD", name: str = "DELTA BEVERAGES", buyer_tin: str = "200112233", buyer_name: str = "ACME HOLDINGS ZIMBABWE", is_valid: bool = True) -> NormalisedLine:
    return NormalisedLine(
        line_id=line_id,
        source_row_number=1,
        supplier_name_raw=name,
        supplier_name_norm=name,
        supplier_name_stripped=name,
        supplier_tin_raw=tin,
        supplier_tin_norm=tin,
        invoice_number_raw=inv,
        invoice_number_norm=inv,
        invoice_date=dt,
        document_type=DocumentType.INVOICE,
        currency=curr,
        net_minor=net,
        vat_minor=vat,
        gross_minor=net + vat,
        buyer_tin_norm=buyer_tin,
        buyer_name_norm=buyer_name,
        validity_is_valid=is_valid
    )

def test_pass_1_exact_match() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)
    z = make_zimra_line("z1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)

    result = reconcile([ap], [z], CLIENT)
    assert len(result.matches) == 1
    assert result.matches[0].pass_id == "P1"
    assert result.matches[0].confidence == 100
    assert len(result.exceptions) == 0

def test_pass_2_amount_tolerance_match() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)
    # 2 cents difference in VAT
    z = make_zimra_line("z1", "1001", "INV100", date(2026, 1, 10), 100000, 15502)

    result = reconcile([ap], [z], CLIENT)
    assert len(result.matches) == 1
    assert result.matches[0].pass_id == "P2"
    assert result.matches[0].confidence == 96

def test_pass_3_date_window_match() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)
    # 2 days difference, invoice number different
    z = make_zimra_line("z1", "1001", "INV999", date(2026, 1, 12), 100000, 15500)

    result = reconcile([ap], [z], CLIENT)
    assert len(result.matches) == 1
    assert result.matches[0].pass_id == "P3"
    assert result.matches[0].confidence == 90

def test_pass_4_name_similarity_match() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500, name="DELTA BEVERAGES HARARE")
    z = make_zimra_line("z1", "9999", "INV100", date(2026, 1, 10), 100000, 15500, name="DELTA BEVERAGES")

    # With config review_threshold=85 (since P4 confidence is 88)
    config = MatchConfig(review_threshold=85)
    result = reconcile([ap], [z], CLIENT, config=config)
    assert len(result.matches) == 1
    assert result.matches[0].pass_id == "P4"
    assert result.matches[0].confidence == 88

    # With default review_threshold=90 -> routed to review_queue for human review
    result_default = reconcile([ap], [z], CLIENT)
    assert len(result_default.review_queue) == 1
    assert result_default.review_queue[0].ap_line.line_id == "ap1"

def test_exception_e1_absent_from_zimra() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)
    result = reconcile([ap], [], CLIENT)

    assert len(result.matches) == 0
    assert len(result.exceptions) == 1
    assert result.exceptions[0].primary_class == ExceptionClass.E1
    assert result.exceptions[0].vat_at_risk_minor == 15500
    assert result.stats.vat_at_risk_by_currency["USD"] == 15500

def test_exception_e2_buyer_tin_mismatch() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)
    z = make_zimra_line("z1", "1001", "INV100", date(2026, 1, 10), 100000, 15500, buyer_tin="999999999")

    result = reconcile([ap], [z], CLIENT)
    assert len(result.matches) == 1
    assert len(result.exceptions) == 1
    assert result.exceptions[0].primary_class == ExceptionClass.E2
    assert result.exceptions[0].vat_at_risk_minor == 15500

def test_exception_e4_invalid_status_in_zimra() -> None:
    ap = make_ap_line("ap1", "1001", "INV100", date(2026, 1, 10), 100000, 15500)
    z = make_zimra_line("z1", "1001", "INV100", date(2026, 1, 10), 100000, 15500, is_valid=False)

    result = reconcile([ap], [z], CLIENT)
    assert len(result.matches) == 1
    assert len(result.exceptions) == 1
    assert result.exceptions[0].primary_class == ExceptionClass.E4

def test_determinism() -> None:
    ap_lines = [
        make_ap_line(f"ap_{i}", f"100{i%5}", f"INV_{1000-i}", date(2026, 1, (i%28)+1), 50000 + i*10, 7750 + i)
        for i in range(50)
    ]
    zimra_lines = [
        make_zimra_line(f"z_{i}", f"100{i%5}", f"INV_{1000-i}", date(2026, 1, (i%28)+1), 50000 + i*10, 7750 + i)
        for i in reversed(range(50))
    ]

    res_first = reconcile(ap_lines, zimra_lines, CLIENT)
    for _ in range(5):
        res_subsequent = reconcile(ap_lines, zimra_lines, CLIENT)
        assert len(res_first.matches) == len(res_subsequent.matches)
        for m1, m2 in zip(res_first.matches, res_subsequent.matches):
            assert m1.ap_line.line_id == m2.ap_line.line_id
            assert m1.zimra_line.line_id == m2.zimra_line.line_id
            assert m1.confidence == m2.confidence
