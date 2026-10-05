import re
import string
from datetime import date, datetime, timedelta
from typing import Any, Optional, Tuple

CORPORATE_SUFFIX_TOKENS = {
    "PVT", "PRIVATE", "LTD", "LIMITED", "T/A", "TA", "PL",
    "CO", "COMPANY", "ENTERPRISES", "INVESTMENTS", "HOLDINGS", "INC", "CORP"
}

CURRENCY_MAPPINGS = {
    "USD": "USD",
    "US$": "USD",
    "$": "USD",
    "ZWG": "ZWG",
    "ZIG": "ZWG",
    "ZWL": "ZWG",
    "ZAR": "ZAR",
    "R": "ZAR",
    "EUR": "EUR",
    "€": "EUR",
    "GBP": "GBP",
    "£": "GBP",
}

def normalise_tin(raw: Optional[str]) -> Optional[str]:
    """FR-NRM-1: Strip all non-digits, preserving digits only."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits if digits else None

def normalise_invoice_number(raw: Optional[str]) -> str:
    """
    FR-NRM-2: Uppercase, strip whitespace, strip [- / \\ . #],
    and strip leading zeros from numeric segments.
    Examples:
      'inv-000452' -> 'INV452'
      'INV/2026/00012' -> 'INV202612'
      '000987' -> '987'
    """
    if not raw:
        return ""
    text = str(raw).upper().strip()
    parts = re.split(r"[\s\-\/\\\.\#]+", text)
    cleaned_parts = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            stripped = p.lstrip("0")
            cleaned_parts.append(stripped if stripped else "0")
        else:
            m = re.search(r"^([A-Z]+)0*(\d+)$", p)
            if m:
                prefix, num = m.groups()
                cleaned_parts.append(f"{prefix}{num}")
            else:
                cleaned_parts.append(p)
    return "".join(cleaned_parts)

def normalise_supplier_name(raw: Optional[str]) -> Tuple[str, str]:
    """
    FR-NRM-3: Uppercase, strip punctuation, collapse whitespace,
    and remove corporate suffix tokens for matching similarity.
    Returns (normalised_full, normalised_stripped).
    """
    if not raw:
        return ("", "")
    text = str(raw).upper().strip()
    # Remove punctuation except word chars and whitespace
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    full_norm = " ".join(tokens)
    
    stripped_tokens = [t for t in tokens if t not in CORPORATE_SUFFIX_TOKENS]
    stripped_norm = " ".join(stripped_tokens) if stripped_tokens else full_norm
    return (full_norm, stripped_norm)

def parse_amount_minor(raw: Any) -> Tuple[Optional[int], bool]:
    """
    FR-NRM-4: Parse amount to integer minor units (cents).
    Handles:
      thousands separators (1,234.50)
      parentheses negatives ((1,234.50))
      trailing CR/DR (1,234.50 CR -> negative, 1,234.50 DR -> positive)
      currency symbols ($1,234.50, US$ 500)
    Returns (amount_minor, is_valid).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return (0, True)
    
    if isinstance(raw, (int, float)):
        # Convert float/int directly, rounding half-up
        cents = int(round(float(raw) * 100))
        return (cents, True)
    
    s = str(raw).strip().upper()
    if not s:
        return (0, True)
        
    is_negative = False
    
    # Check for parentheses: (1,234.50)
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
        
    # Check for trailing CR / DR
    if s.endswith("CR"):
        is_negative = True
        s = s[:-2].strip()
    elif s.endswith("DR"):
        s = s[:-2].strip()
        
    # Check for leading minus sign
    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    elif s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()
        
    # Strip currency prefixes / symbols
    s = re.sub(r"[^\d\.,]", "", s)
    
    # Normalize thousand separators and decimals
    # Standard format: 1,234.56 or 1234.56
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # European format: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:
            # Standard format: 1,234.56
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        # Check if single comma is decimal or thousand sep
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
            
    try:
        val = float(s)
        cents = int(round(val * 100))
        if is_negative:
            cents = -abs(cents)
        return (cents, True)
    except (ValueError, TypeError):
        return (None, False)

def normalise_currency(raw: Optional[str], default: str = "USD") -> str:
    """FR-NRM-5: Normalise to ISO currency code."""
    if not raw:
        return default
    cleaned = str(raw).strip().upper()
    return CURRENCY_MAPPINGS.get(cleaned, cleaned)

def parse_date(raw: Any) -> Tuple[Optional[date], bool]:
    """
    FR-NRM-6: Parse DD/MM/YYYY, YYYY-MM-DD, DD-MMM-YY, Excel serial.
    Resolves ambiguous dates like 01/02/2026 as 1 February 2026 (DD/MM, Zimbabwe convention).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return (None, False)
        
    if isinstance(raw, date):
        return (raw, True)
    if isinstance(raw, datetime):
        return (raw.date(), True)
        
    # Excel serial number handling (e.g. 45678)
    if isinstance(raw, (int, float)):
        try:
            excel_serial = float(raw)
            # Excel start date is 1899-12-30 due to leap year bug
            epoch = datetime(1899, 12, 30)
            res_date = (epoch + timedelta(days=excel_serial)).date()
            return (res_date, True)
        except Exception:
            return (None, False)
            
    s = str(raw).strip()
    
    # Try common explicit date formats
    formats = [
        "%d/%m/%Y",       # 31/01/2026 (Zimbabwe default)
        "%d-%m-%Y",       # 31-01-2026
        "%Y-%m-%d",       # 2026-01-31 (ISO)
        "%Y/%m/%d",       # 2026/01/31
        "%d-%b-%y",       # 31-Jan-26
        "%d-%b-%Y",       # 31-Jan-2026
        "%d %b %Y",       # 31 Jan 2026
        "%d %B %Y",       # 31 January 2026
        "%d%m%Y",         # 31012026
        "%Y%m%d",         # 20260131
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return (dt.date(), True)
        except ValueError:
            continue
            
    return (None, False)
