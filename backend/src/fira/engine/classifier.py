from typing import Optional, Sequence
from rapidfuzz import fuzz

from fira.engine.types import (
    NormalisedLine, MatchRecord, ExceptionRecord, ExceptionClass,
    ClientParticulars, MatchConfig, DocumentType, ExceptionStatus
)

class Classifier:
    """Exception and VAT-at-risk classification engine."""

    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()

    def classify(
        self,
        matches: Sequence[MatchRecord],
        ap_only: Sequence[NormalisedLine],
        zimra_only: Sequence[NormalisedLine],
        client: ClientParticulars
    ) -> list[ExceptionRecord]:
        exceptions: list[ExceptionRecord] = []

        # ---------------------------------------------------------------------
        # 1. Classify AP-Only lines (E1, E6, E7)
        # ---------------------------------------------------------------------
        for ap in ap_only:
            # Check E6: Orphan credit / debit note
            if ap.document_type in (DocumentType.CREDIT_NOTE, DocumentType.DEBIT_NOTE):
                exceptions.append(ExceptionRecord(
                    ap_line=ap,
                    zimra_line=None,
                    match_record=None,
                    primary_class=ExceptionClass.E6,
                    all_classes=[ExceptionClass.E6],
                    rule_id="RULE_E6_ORPHAN_CREDIT_DEBIT_AP",
                    evidence={
                        "reason": f"Orphan {ap.document_type.value} absent from ZIMRA claim list",
                        "document_type": ap.document_type.value,
                        "invoice_number": ap.invoice_number_norm,
                        "vat_minor": ap.vat_minor
                    },
                    vat_at_risk_minor=abs(ap.vat_minor),
                    currency=ap.currency,
                    is_recoverable=True,
                    is_advisory=False
                ))
            else:
                # E1: Invoice absent from ZIMRA
                all_cls = [ExceptionClass.E1]
                evidence = {
                    "reason": "Invoice present in accounts payable ledger but absent from ZIMRA FDMS list",
                    "supplier_name": ap.supplier_name_norm,
                    "supplier_tin": ap.supplier_tin_norm,
                    "invoice_number": ap.invoice_number_norm,
                    "invoice_date": str(ap.invoice_date),
                    "vat_minor": ap.vat_minor
                }
                
                # Check if also has advisory E7
                if self._has_e7_keyword(ap):
                    all_cls.append(ExceptionClass.E7)
                    evidence["e7_warning"] = "Matches non-qualifying expense category keywords"

                exceptions.append(ExceptionRecord(
                    ap_line=ap,
                    zimra_line=None,
                    match_record=None,
                    primary_class=ExceptionClass.E1,
                    all_classes=all_cls,
                    rule_id="RULE_E1_ABSENT_FROM_ZIMRA",
                    evidence=evidence,
                    vat_at_risk_minor=ap.vat_minor,
                    currency=ap.currency,
                    is_recoverable=True,
                    is_advisory=False
                ))

        # ---------------------------------------------------------------------
        # 2. Classify Matched pairs (E2, E3, E4, E5, E7)
        # ---------------------------------------------------------------------
        for m in matches:
            ap = m.ap_line
            z = m.zimra_line
            all_classes: list[ExceptionClass] = []
            evidence: dict = {"match_pass": m.pass_id, "confidence": m.confidence}
            vat_at_risk = 0
            is_advisory = False

            # Check E4: Invalid in ZIMRA
            if not z.validity_is_valid:
                all_classes.append(ExceptionClass.E4)
                evidence["e4_validity_status"] = z.validity_status_raw
                vat_at_risk = max(vat_at_risk, ap.vat_minor)

            # Check E2: Buyer TIN blank or mismatch
            if not z.buyer_tin_norm or (z.buyer_tin_norm != client.tin_normalised):
                all_classes.append(ExceptionClass.E2)
                evidence["e2_expected_buyer_tin"] = client.tin_normalised
                evidence["e2_actual_buyer_tin"] = z.buyer_tin_norm
                vat_at_risk = max(vat_at_risk, ap.vat_minor)

            # Check E3: Buyer name substantial mismatch
            if z.buyer_name_norm:
                sim_legal = fuzz.token_set_ratio(z.buyer_name_norm, client.legal_name_norm)
                sim_trade = fuzz.token_set_ratio(z.buyer_name_norm, client.trading_name_norm) if client.trading_name_norm else 0
                max_sim = max(sim_legal, sim_trade)
                if max_sim < self.config.buyer_name_similarity_threshold:
                    all_classes.append(ExceptionClass.E3)
                    evidence["e3_expected_buyer_name"] = client.legal_name_norm
                    evidence["e3_actual_buyer_name"] = z.buyer_name_norm
                    evidence["e3_similarity_score"] = max_sim
                    vat_at_risk = max(vat_at_risk, ap.vat_minor)

            # Check E5: Value or VAT rate discrepancy
            vat_diff = abs(ap.vat_minor - z.vat_minor)
            if vat_diff > self.config.amount_tolerance_cents:
                all_classes.append(ExceptionClass.E5)
                evidence["e5_ap_vat_minor"] = ap.vat_minor
                evidence["e5_zimra_vat_minor"] = z.vat_minor
                evidence["e5_vat_discrepancy_minor"] = vat_diff
                vat_at_risk = max(vat_at_risk, vat_diff)

            # Check E7: Advisory non-qualifying expense category
            if self._has_e7_keyword(ap):
                all_classes.append(ExceptionClass.E7)
                evidence["e7_expense_category"] = ap.expense_category
                evidence["e7_description"] = ap.description
                if not vat_at_risk:
                    vat_at_risk = ap.vat_minor
                    is_advisory = True

            if all_classes:
                # Primary class hierarchy: E4 > E1 > E2 > E3 > E5 > E6 > E7
                hierarchy = [
                    ExceptionClass.E4, ExceptionClass.E1, ExceptionClass.E2,
                    ExceptionClass.E3, ExceptionClass.E5, ExceptionClass.E6, ExceptionClass.E7
                ]
                primary = next(c for c in hierarchy if c in all_classes)

                exceptions.append(ExceptionRecord(
                    ap_line=ap,
                    zimra_line=z,
                    match_record=m,
                    primary_class=primary,
                    all_classes=all_classes,
                    rule_id=f"RULE_{primary.value}_MATCHED_LINE",
                    evidence=evidence,
                    vat_at_risk_minor=vat_at_risk,
                    currency=ap.currency,
                    is_recoverable=True if primary != ExceptionClass.E7 else False,
                    is_advisory=is_advisory or (primary == ExceptionClass.E7)
                ))

        # ---------------------------------------------------------------------
        # 3. Classify ZIMRA-Only lines (Unclaimed / orphan records)
        # ---------------------------------------------------------------------
        for z in zimra_only:
            if z.document_type in (DocumentType.CREDIT_NOTE, DocumentType.DEBIT_NOTE):
                exceptions.append(ExceptionRecord(
                    ap_line=None,
                    zimra_line=z,
                    match_record=None,
                    primary_class=ExceptionClass.E6,
                    all_classes=[ExceptionClass.E6],
                    rule_id="RULE_E6_ORPHAN_CREDIT_DEBIT_ZIMRA",
                    evidence={
                        "reason": f"ZIMRA {z.document_type.value} has no matching AP invoice in ledger",
                        "supplier_name": z.supplier_name_norm,
                        "invoice_number": z.invoice_number_norm,
                        "vat_minor": z.vat_minor
                    },
                    vat_at_risk_minor=abs(z.vat_minor),
                    currency=z.currency,
                    is_recoverable=True,
                    is_advisory=False
                ))

        return exceptions

    def _has_e7_keyword(self, line: NormalisedLine) -> bool:
        """Check if expense category or description matches non-qualifying keywords."""
        text_to_check = f"{line.expense_category or ''} {line.description or ''}".lower()
        if not text_to_check.strip():
            return False
        for kw in self.config.non_qualifying_keywords:
            if kw.lower() in text_to_check:
                return True
        return False
