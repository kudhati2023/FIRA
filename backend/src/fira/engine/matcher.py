import math
from datetime import date
from typing import Sequence, Optional, Tuple
from rapidfuzz import fuzz

from fira.engine.types import (
    NormalisedLine, MatchRecord, MatchCandidate, AmbiguousItem,
    ManualDecision, MatchConfig, DocumentType
)

def sort_key(line: NormalisedLine) -> tuple[date, str, str, int, int]:
    """HC-4: Strict deterministic sort key for lines."""
    return (
        line.invoice_date,
        line.supplier_tin_norm or "",
        line.invoice_number_norm,
        line.net_minor,
        line.source_row_number
    )

def is_amount_within_tolerance(ap_minor: int, zimra_minor: int, config: MatchConfig) -> bool:
    """Check if amounts are within configured absolute minor units or percentage tolerance."""
    diff = abs(ap_minor - zimra_minor)
    max_val = max(abs(ap_minor), abs(zimra_minor))
    pct_allowed = int(round(max_val * (config.amount_tolerance_percentage / 100.0)))
    allowed = max(config.amount_tolerance_cents, pct_allowed)
    return diff <= allowed

def calculate_penalties(ap: NormalisedLine, zimra: NormalisedLine) -> list[tuple[str, int]]:
    """Calculate confidence penalties according to §6.4."""
    penalties: list[tuple[str, int]] = []
    
    # Currency differs
    if ap.currency != zimra.currency:
        penalties.append(("Currency mismatch", 40))
        
    # Document types differ
    if ap.document_type != zimra.document_type:
        penalties.append(("Document type mismatch", 30))
        
    # Date difference > 7 days
    date_diff = abs((ap.invoice_date - zimra.invoice_date).days)
    if date_diff > 7:
        penalties.append(("Date difference > 7 days", 15))
        
    # Supplier TIN present on one side only
    has_ap_tin = bool(ap.supplier_tin_norm)
    has_zimra_tin = bool(zimra_tin_norm := zimra.supplier_tin_norm)
    if has_ap_tin != has_zimra_tin:
        penalties.append(("Supplier TIN present on one side only", 10))
        
    # Amount difference between 0.5% and 2.0%
    if ap.vat_minor != zimra.vat_minor:
        max_val = max(abs(ap.vat_minor), abs(zimra.vat_minor))
        if max_val > 0:
            diff_pct = (abs(ap.vat_minor - zimra.vat_minor) / max_val) * 100.0
            if 0.5 < diff_pct <= 2.0:
                penalties.append(("Amount difference between 0.5% and 2.0%", 8))
                
    return penalties

def compute_final_confidence(base_confidence: int, penalties: list[tuple[str, int]]) -> int:
    """Compute floored confidence score."""
    total_penalty = sum(p[1] for p in penalties)
    return max(0, base_confidence - total_penalty)

class Matcher:
    """Deterministic Multi-Pass Matching Engine."""

    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()

    def run_matching(
        self,
        ap_lines: Sequence[NormalisedLine],
        zimra_lines: Sequence[NormalisedLine],
        manual_decisions: Sequence[ManualDecision] = ()
    ) -> Tuple[list[MatchRecord], list[NormalisedLine], list[NormalisedLine], list[AmbiguousItem]]:
        # 1. Deterministic sort of input sets
        sorted_ap = sorted(ap_lines, key=sort_key)
        sorted_zimra = sorted(zimra_lines, key=sort_key)

        matched_ap_ids: set[str] = set()
        matched_zimra_ids: set[str] = set()
        matches: list[MatchRecord] = []
        review_queue: list[AmbiguousItem] = []

        zimra_lookup = {line.line_id: line for line in sorted_zimra}
        ap_lookup = {line.line_id: line for line in sorted_ap}

        # ---------------------------------------------------------------------
        # Pass 0: Manual Operator Decisions
        # ---------------------------------------------------------------------
        for dec in manual_decisions:
            if not dec.is_match:
                # Explicit exclusion (e.g. definitely not a match)
                continue
            if dec.ap_line_id in ap_lookup and dec.zimra_line_id in zimra_lookup:
                ap_line = ap_lookup[dec.ap_line_id]
                zimra_line = zimra_lookup[dec.zimra_line_id]
                if ap_line.line_id not in matched_ap_ids and zimra_line.line_id not in matched_zimra_ids:
                    matches.append(MatchRecord(
                        ap_line=ap_line,
                        zimra_line=zimra_line,
                        pass_id="P0",
                        confidence=100,
                        is_manual=True,
                        note=dec.note
                    ))
                    matched_ap_ids.add(ap_line.line_id)
                    matched_zimra_ids.add(zimra_line.line_id)

        # Helper to get currently unmatched candidate pools
        def get_unmatched():
            unmatched_ap = [l for l in sorted_ap if l.line_id not in matched_ap_ids]
            unmatched_zimra = [l for l in sorted_zimra if l.line_id not in matched_zimra_ids]
            return unmatched_ap, unmatched_zimra

        # ---------------------------------------------------------------------
        # Pass 1: TIN + Invoice No + Exact VAT + Same Currency (Base 100)
        # ---------------------------------------------------------------------
        unmatched_ap, unmatched_zimra = get_unmatched()
        for ap in unmatched_ap:
            if not ap.supplier_tin_norm or not ap.invoice_number_norm:
                continue
            candidates = []
            for z in unmatched_zimra:
                if (z.supplier_tin_norm == ap.supplier_tin_norm and
                    z.invoice_number_norm == ap.invoice_number_norm and
                    z.vat_minor == ap.vat_minor and
                    z.currency == ap.currency):
                    penalties = calculate_penalties(ap, z)
                    conf = compute_final_confidence(100, penalties)
                    candidates.append(MatchCandidate(z, "P1", 100, penalties, conf))
            
            if len(candidates) == 1:
                cand = candidates[0]
                matches.append(MatchRecord(ap, cand.zimra_line, "P1", cand.final_confidence))
                matched_ap_ids.add(ap.line_id)
                matched_zimra_ids.add(cand.zimra_line.line_id)
                unmatched_zimra = [z for z in unmatched_zimra if z.line_id != cand.zimra_line.line_id]
            elif len(candidates) > 1:
                review_queue.append(AmbiguousItem(ap, candidates))
                matched_ap_ids.add(ap.line_id)

        # ---------------------------------------------------------------------
        # Pass 2: TIN + Invoice No + Amounts Within Tolerance (Base 96)
        # ---------------------------------------------------------------------
        unmatched_ap, unmatched_zimra = get_unmatched()
        for ap in unmatched_ap:
            if not ap.supplier_tin_norm or not ap.invoice_number_norm:
                continue
            candidates = []
            for z in unmatched_zimra:
                if (z.supplier_tin_norm == ap.supplier_tin_norm and
                    z.invoice_number_norm == ap.invoice_number_norm and
                    is_amount_within_tolerance(ap.vat_minor, z.vat_minor, self.config)):
                    penalties = calculate_penalties(ap, z)
                    conf = compute_final_confidence(96, penalties)
                    candidates.append(MatchCandidate(z, "P2", 96, penalties, conf))
                    
            if len(candidates) == 1:
                cand = candidates[0]
                matches.append(MatchRecord(ap, cand.zimra_line, "P2", cand.final_confidence))
                matched_ap_ids.add(ap.line_id)
                matched_zimra_ids.add(cand.zimra_line.line_id)
                unmatched_zimra = [z for z in unmatched_zimra if z.line_id != cand.zimra_line.line_id]
            elif len(candidates) > 1:
                review_queue.append(AmbiguousItem(ap, candidates))
                matched_ap_ids.add(ap.line_id)

        # ---------------------------------------------------------------------
        # Pass 3: TIN + Exact VAT + Date within +-3 days (Base 90)
        # ---------------------------------------------------------------------
        unmatched_ap, unmatched_zimra = get_unmatched()
        for ap in unmatched_ap:
            if not ap.supplier_tin_norm:
                continue
            candidates = []
            for z in unmatched_zimra:
                if (z.supplier_tin_norm == ap.supplier_tin_norm and
                    z.vat_minor == ap.vat_minor and
                    abs((ap.invoice_date - z.invoice_date).days) <= self.config.date_window_p3_days):
                    penalties = calculate_penalties(ap, z)
                    conf = compute_final_confidence(90, penalties)
                    candidates.append(MatchCandidate(z, "P3", 90, penalties, conf))
                    
            if len(candidates) == 1:
                cand = candidates[0]
                matches.append(MatchRecord(ap, cand.zimra_line, "P3", cand.final_confidence))
                matched_ap_ids.add(ap.line_id)
                matched_zimra_ids.add(cand.zimra_line.line_id)
                unmatched_zimra = [z for z in unmatched_zimra if z.line_id != cand.zimra_line.line_id]
            elif len(candidates) > 1:
                review_queue.append(AmbiguousItem(ap, candidates))
                matched_ap_ids.add(ap.line_id)

        # ---------------------------------------------------------------------
        # Pass 4: Name similarity >= 92 + Invoice No + Amount tolerance (Base 88)
        # ---------------------------------------------------------------------
        unmatched_ap, unmatched_zimra = get_unmatched()
        for ap in unmatched_ap:
            if not ap.invoice_number_norm:
                continue
            candidates = []
            for z in unmatched_zimra:
                if (z.invoice_number_norm == ap.invoice_number_norm and
                    is_amount_within_tolerance(ap.vat_minor, z.vat_minor, self.config)):
                    sim = fuzz.token_set_ratio(ap.supplier_name_stripped, z.supplier_name_stripped)
                    if sim >= self.config.name_similarity_p4_threshold:
                        penalties = calculate_penalties(ap, z)
                        conf = compute_final_confidence(88, penalties)
                        candidates.append(MatchCandidate(z, "P4", 88, penalties, conf))
                        
            if len(candidates) == 1:
                cand = candidates[0]
                matches.append(MatchRecord(ap, cand.zimra_line, "P4", cand.final_confidence))
                matched_ap_ids.add(ap.line_id)
                matched_zimra_ids.add(cand.zimra_line.line_id)
                unmatched_zimra = [z for z in unmatched_zimra if z.line_id != cand.zimra_line.line_id]
            elif len(candidates) > 1:
                review_queue.append(AmbiguousItem(ap, candidates))
                matched_ap_ids.add(ap.line_id)

        # ---------------------------------------------------------------------
        # Pass 5: Name similarity >= 88 + Exact VAT + Date within +-7 days (Base 80)
        # ---------------------------------------------------------------------
        unmatched_ap, unmatched_zimra = get_unmatched()
        for ap in unmatched_ap:
            candidates = []
            for z in unmatched_zimra:
                if (z.vat_minor == ap.vat_minor and
                    abs((ap.invoice_date - z.invoice_date).days) <= self.config.date_window_p5_days):
                    sim = fuzz.token_set_ratio(ap.supplier_name_stripped, z.supplier_name_stripped)
                    if sim >= self.config.name_similarity_p5_threshold:
                        penalties = calculate_penalties(ap, z)
                        conf = compute_final_confidence(80, penalties)
                        candidates.append(MatchCandidate(z, "P5", 80, penalties, conf))
                        
            if len(candidates) == 1:
                cand = candidates[0]
                matches.append(MatchRecord(ap, cand.zimra_line, "P5", cand.final_confidence))
                matched_ap_ids.add(ap.line_id)
                matched_zimra_ids.add(cand.zimra_line.line_id)
                unmatched_zimra = [z for z in unmatched_zimra if z.line_id != cand.zimra_line.line_id]
            elif len(candidates) > 1:
                review_queue.append(AmbiguousItem(ap, candidates))
                matched_ap_ids.add(ap.line_id)

        # ---------------------------------------------------------------------
        # Post-Processing: Review Threshold check (§6.4, FR-REC-3)
        # ---------------------------------------------------------------------
        final_matches: list[MatchRecord] = []
        for m in matches:
            if m.confidence < self.config.review_threshold and not m.is_manual:
                review_queue.append(AmbiguousItem(
                    ap_line=m.ap_line,
                    candidates=[MatchCandidate(m.zimra_line, m.pass_id, 100, [], m.confidence)],
                    reason=f"Match confidence {m.confidence}% below review threshold {self.config.review_threshold}%"
                ))
            else:
                final_matches.append(m)

        # Final sets
        final_ap_only = [l for l in sorted_ap if l.line_id not in matched_ap_ids]
        final_zimra_only = [l for l in sorted_zimra if l.line_id not in matched_zimra_ids]

        return final_matches, final_ap_only, final_zimra_only, review_queue
