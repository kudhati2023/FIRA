from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any, Sequence

class DocumentType(str, Enum):
    INVOICE = "INVOICE"
    CREDIT_NOTE = "CREDIT_NOTE"
    DEBIT_NOTE = "DEBIT_NOTE"

class LineStatus(str, Enum):
    OK = "OK"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    EXCLUDED = "EXCLUDED"

class ExceptionClass(str, Enum):
    E1 = "E1"  # Absent from ZIMRA
    E2 = "E2"  # Buyer TIN blank or mismatch
    E3 = "E3"  # Buyer Name / VAT number mismatch with registered particulars
    E4 = "E4"  # Marked Not Valid in ZIMRA data
    E5 = "E5"  # Value or VAT rate discrepancy
    E6 = "E6"  # Credit/debit note not linked to original invoice
    E7 = "E7"  # Non-qualifying expense category (advisory)

class ExceptionStatus(str, Enum):
    OPEN = "OPEN"
    NOTIFIED = "NOTIFIED"
    SUPPLIER_ACKNOWLEDGED = "SUPPLIER_ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    UNRECOVERABLE = "UNRECOVERABLE"
    DISMISSED = "DISMISSED"

class SupplierOutcome(str, Enum):
    PENDING = "PENDING"
    CORRECTED = "CORRECTED"
    REFUSED = "REFUSED"
    NO_RESPONSE = "NO_RESPONSE"
    PARTIAL = "PARTIAL"

@dataclass(frozen=True, slots=True)
class NormalisedLine:
    line_id: str
    source_row_number: int
    supplier_name_raw: str
    supplier_name_norm: str
    supplier_name_stripped: str
    supplier_tin_raw: Optional[str]
    supplier_tin_norm: Optional[str]
    invoice_number_raw: str
    invoice_number_norm: str
    invoice_date: date
    document_type: DocumentType
    currency: str
    net_minor: int
    vat_minor: int
    gross_minor: int
    expense_category: Optional[str] = None
    description: Optional[str] = None
    buyer_name_raw: Optional[str] = None
    buyer_name_norm: Optional[str] = None
    buyer_tin_raw: Optional[str] = None
    buyer_tin_norm: Optional[str] = None
    buyer_vat_number: Optional[str] = None
    validity_status_raw: Optional[str] = None
    validity_is_valid: bool = True
    device_id: Optional[str] = None
    receipt_global_no: Optional[str] = None
    fiscal_day_no: Optional[str] = None
    status: LineStatus = LineStatus.OK
    raw_payload: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class ClientParticulars:
    client_id: str
    legal_name_norm: str
    trading_name_norm: Optional[str]
    tin_normalised: str
    vat_number: Optional[str] = None

@dataclass(frozen=True, slots=True)
class ManualDecision:
    ap_line_id: str
    zimra_line_id: Optional[str]  # None if explicit exclusion
    is_match: bool  # True for force-match, False for definite non-match
    note: Optional[str] = None

@dataclass(frozen=True, slots=True)
class MatchCandidate:
    zimra_line: NormalisedLine
    pass_id: str
    base_confidence: int
    penalties: list[tuple[str, int]]
    final_confidence: int

@dataclass(frozen=True, slots=True)
class MatchRecord:
    ap_line: NormalisedLine
    zimra_line: NormalisedLine
    pass_id: str
    confidence: int
    is_manual: bool = False
    note: Optional[str] = None

@dataclass(frozen=True, slots=True)
class AmbiguousItem:
    ap_line: NormalisedLine
    candidates: list[MatchCandidate]
    reason: str = "Multiple candidate lines matched with identical score"

@dataclass(frozen=True, slots=True)
class ExceptionRecord:
    ap_line: Optional[NormalisedLine]
    zimra_line: Optional[NormalisedLine]
    match_record: Optional[MatchRecord]
    primary_class: ExceptionClass
    all_classes: list[ExceptionClass]
    rule_id: str
    evidence: dict[str, Any]
    vat_at_risk_minor: int
    currency: str
    is_recoverable: bool
    is_advisory: bool
    status: ExceptionStatus = ExceptionStatus.OPEN

@dataclass(frozen=True)
class MatchConfig:
    review_threshold: int = 90
    amount_tolerance_cents: int = 2
    amount_tolerance_percentage: float = 0.5
    date_window_p3_days: int = 3
    date_window_p5_days: int = 7
    name_similarity_p4_threshold: float = 92.0
    name_similarity_p5_threshold: float = 88.0
    buyer_name_similarity_threshold: float = 90.0
    non_qualifying_keywords: tuple[str, ...] = (
        "entertainment",
        "passenger",
        "motor vehicle",
        "hospitality",
        "club",
        "lunch",
        "golf",
        "beverage",
        "alcohol",
        "staff function"
    )
    accepted_valid_statuses: tuple[str, ...] = (
        "VALID",
        "APPROVED",
        "SUCCESS",
        "FISCALISED",
        "ACCEPTED"
    )

@dataclass(frozen=True, slots=True)
class ReconciliationStats:
    total_ap_lines: int
    total_zimra_lines: int
    matched_count: int
    ap_only_count: int
    zimra_only_count: int
    review_queue_count: int
    exceptions_count: int
    vat_at_risk_by_currency: dict[str, int]
    execution_duration_ms: int

@dataclass(frozen=True)
class ReconciliationResult:
    matches: list[MatchRecord]
    ap_only: list[NormalisedLine]
    zimra_only: list[NormalisedLine]
    review_queue: list[AmbiguousItem]
    exceptions: list[ExceptionRecord]
    stats: ReconciliationStats
