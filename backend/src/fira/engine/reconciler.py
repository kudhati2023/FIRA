import time
from typing import Sequence, Optional
from collections import defaultdict

from fira.engine.types import (
    NormalisedLine, ClientParticulars, ManualDecision, MatchConfig,
    ReconciliationResult, ReconciliationStats, MatchRecord,
    ExceptionRecord, AmbiguousItem
)
from fira.engine.matcher import Matcher
from fira.engine.classifier import Classifier

def reconcile(
    ap_lines: Sequence[NormalisedLine],
    zimra_lines: Sequence[NormalisedLine],
    client: ClientParticulars,
    manual_decisions: Sequence[ManualDecision] = (),
    config: Optional[MatchConfig] = None
) -> ReconciliationResult:
    """
    Execute deterministic end-to-end reconciliation:
    1. Multi-pass matching P0-P5
    2. Exception classification E1-E7
    3. Currency-segregated stats computation
    """
    start_time = time.perf_counter()
    cfg = config or MatchConfig()

    matcher = Matcher(cfg)
    classifier = Classifier(cfg)

    # 1. Run Matching Engine
    matches, ap_only, zimra_only, review_queue = matcher.run_matching(
        ap_lines=ap_lines,
        zimra_lines=zimra_lines,
        manual_decisions=manual_decisions
    )

    # 2. Run Exception Classifier
    exceptions = classifier.classify(
        matches=matches,
        ap_only=ap_only,
        zimra_only=zimra_only,
        client=client
    )

    # 3. Compute Currency-Segregated VAT at Risk (FR-VAL-4)
    vat_at_risk_by_curr: dict[str, int] = defaultdict(int)
    for exc in exceptions:
        if not exc.is_advisory:
            vat_at_risk_by_curr[exc.currency] += exc.vat_at_risk_minor

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    stats = ReconciliationStats(
        total_ap_lines=len(ap_lines),
        total_zimra_lines=len(zimra_lines),
        matched_count=len(matches),
        ap_only_count=len(ap_only),
        zimra_only_count=len(zimra_only),
        review_queue_count=len(review_queue),
        exceptions_count=len(exceptions),
        vat_at_risk_by_currency=dict(vat_at_risk_by_curr),
        execution_duration_ms=duration_ms
    )

    return ReconciliationResult(
        matches=matches,
        ap_only=ap_only,
        zimra_only=zimra_only,
        review_queue=review_queue,
        exceptions=exceptions,
        stats=stats
    )
