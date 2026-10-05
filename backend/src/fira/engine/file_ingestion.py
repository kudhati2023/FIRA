import csv
import io
import re
import uuid
from datetime import date, datetime
from typing import Any, BinaryIO, Dict, List, Optional, Tuple
import pandas as pd

from fira.engine.normalisation import normalise_supplier_name, normalise_tin, normalise_invoice_number


def clean_col_name(name: Any) -> str:
    """Standardize column header string for robust matching."""
    s = str(name).strip().lower()
    return re.sub(r"[\s\-_\./#]+", "_", s)


def match_header_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    """Find column matching any of the candidate keywords with exact-match precedence."""
    cleaned_map = {clean_col_name(c): c for c in columns}
    # Pass 1: Exact matches first
    for cand in candidates:
        cand_clean = clean_col_name(cand)
        for c_clean, original in cleaned_map.items():
            if cand_clean == c_clean:
                return original

    # Pass 2: Word boundary / substring matches with collision guards
    for cand in candidates:
        cand_clean = clean_col_name(cand)
        for c_clean, original in cleaned_map.items():
            if cand_clean in c_clean:
                # Disallow matching "supplier" or "taxpayer" to "supplier_tin"
                if cand_clean in ["supplier", "vendor", "taxpayer", "customer", "buyer", "client"] and any(
                    k in c_clean for k in ["tin", "tax_no", "pin", "bpn", "vat_no", "id"]
                ):
                    continue
                return original
    return None


def parse_date_value(val: Any) -> date:
    """Parse cell value into Python date object."""
    if isinstance(val, (datetime, date)):
        return val.date() if isinstance(val, datetime) else val
    if pd.isna(val) or val is None:
        return date.today()

    val_str = str(val).strip()
    # If date string has timestamps e.g. "2026-01-10 00:00:00"
    if " " in val_str:
        val_str = val_str.split(" ")[0]

    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    return date.today()


def parse_amount_minor(val: Any) -> int:
    """Convert amount into integer minor units (cents)."""
    if pd.isna(val) or val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(round(float(val) * 100))

    val_str = str(val).strip()
    cleaned = re.sub(r"[^\d.-]", "", val_str)
    if not cleaned or cleaned == "-":
        return 0
    try:
        return int(round(float(cleaned) * 100))
    except (ValueError, TypeError):
        return 0


def read_tabular_stream(file_stream: BinaryIO, ext: str) -> pd.DataFrame:
    """Load uploaded file stream into Pandas DataFrame."""
    ext_lower = ext.lower()
    file_stream.seek(0)
    if ext_lower == ".csv":
        try:
            # Try reading sample to detect delimiter
            sample = file_stream.read(2048).decode("utf-8", errors="ignore")
            file_stream.seek(0)
            delimiter = ","
            if sample:
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
                    delimiter = dialect.delimiter
                except Exception:
                    delimiter = ","
            df = pd.read_csv(file_stream, sep=delimiter, dtype=str, keep_default_na=False)
        except Exception:
            file_stream.seek(0)
            df = pd.read_csv(file_stream, dtype=str, keep_default_na=False)
    elif ext_lower in [".xlsx", ".xls"]:
        df = pd.read_excel(file_stream, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported tabular extension: {ext}")
    return df


def parse_ap_ledger_file(
    file_stream: BinaryIO,
    ext: str,
    default_currency: str = "USD",
) -> List[Dict[str, Any]]:
    """
    Parse an Accounts Payable (AP) purchase ledger file into structured line dicts.
    """
    df = read_tabular_stream(file_stream, ext)
    if df.empty:
        return []

    cols = list(df.columns)

    col_supp = match_header_column(cols, ["supplier_name", "supplier", "vendor", "account_name", "creditor", "payee", "name"])
    col_tin = match_header_column(cols, ["supplier_tin", "tin", "bpn", "pin", "tax_no", "tax_id", "vat_no"])
    col_inv = match_header_column(cols, ["invoice_number", "invoice_no", "inv_no", "invoice", "inv", "reference", "doc_no", "bill_no"])
    col_date = match_header_column(cols, ["invoice_date", "date", "inv_date", "tx_date", "txn_date", "bill_date"])
    col_gross = match_header_column(cols, ["gross_amount", "gross", "total_amount", "total", "amount", "total_due", "invoice_amount"])
    col_vat = match_header_column(cols, ["vat_amount", "vat", "tax_amount", "tax", "vat_15", "vat_15_5"])
    col_net = match_header_column(cols, ["net_amount", "net", "subtotal", "sub_total", "exclusive_amount"])
    col_curr = match_header_column(cols, ["currency", "curr"])
    col_cat = match_header_column(cols, ["category", "expense_category", "expense_type", "account", "description", "item"])

    parsed_lines = []
    for idx, row in df.iterrows():
        # Get raw values
        supp_name = str(row[col_supp]).strip() if col_supp and row[col_supp] else ""
        if not supp_name or supp_name.lower() in ["total", "subtotal", "grand total"]:
            continue

        raw_tin = str(row[col_tin]).strip() if col_tin and row[col_tin] else ""
        raw_inv = str(row[col_inv]).strip() if col_inv and row[col_inv] else f"INV-{idx + 1}"
        inv_date = parse_date_value(row[col_date]) if col_date else date.today()

        gross_minor = parse_amount_minor(row[col_gross]) if col_gross else 0
        vat_minor = parse_amount_minor(row[col_vat]) if col_vat else 0
        net_minor = parse_amount_minor(row[col_net]) if col_net else 0

        # Math inference if one component is missing
        if gross_minor and not vat_minor and not net_minor:
            vat_minor = int(round(gross_minor * 0.155 / 1.155)) if inv_date >= date(2026, 1, 1) else int(round(gross_minor * 0.150 / 1.150))
            net_minor = gross_minor - vat_minor
        elif net_minor and not gross_minor:
            vat_minor = int(round(net_minor * 0.155)) if inv_date >= date(2026, 1, 1) else int(round(net_minor * 0.150))
            gross_minor = net_minor + vat_minor
        elif gross_minor and net_minor and not vat_minor:
            vat_minor = gross_minor - net_minor

        # Currency
        curr = default_currency
        if col_curr and row[col_curr]:
            curr_str = str(row[col_curr]).strip().upper()
            if "ZWG" in curr_str or "ZIG" in curr_str:
                curr = "ZWG"
            elif "USD" in curr_str:
                curr = "USD"

        cat = str(row[col_cat]).strip() if col_cat and row[col_cat] else "General Expense"

        parsed_lines.append({
            "source_row_number": idx + 1,
            "supplier_name_raw": supp_name,
            "supplier_name_norm": normalise_supplier_name(supp_name)[0],
            "supplier_tin_raw": raw_tin or None,
            "supplier_tin_norm": normalise_tin(raw_tin) if raw_tin else None,
            "invoice_number_raw": raw_inv,
            "invoice_number_norm": normalise_invoice_number(raw_inv),
            "invoice_date": inv_date,
            "currency": curr,
            "net_minor": net_minor,
            "vat_minor": vat_minor,
            "gross_minor": gross_minor,
            "expense_category": cat,
            "description": f"Ledger import: {cat}",
        })

    return parsed_lines


def parse_zimra_claim_file(
    file_stream: BinaryIO,
    ext: str,
    default_currency: str = "USD",
    client_name: Optional[str] = None,
    client_tin: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Parse an official ZIMRA Fiscal Data Management System (FDMS) claim list export file.
    """
    df = read_tabular_stream(file_stream, ext)
    if df.empty:
        return []

    cols = list(df.columns)

    col_supp = match_header_column(cols, ["supplier_name", "supplier", "taxpayer_name", "vendor", "name"])
    col_tin = match_header_column(cols, ["supplier_tin", "tin", "bpn", "pin", "tax_no", "tax_id"])
    col_inv = match_header_column(cols, ["fiscal_invoice_number", "invoice_number", "invoice_no", "inv_no", "invoice", "inv", "reference", "doc_no"])
    col_date = match_header_column(cols, ["fiscal_date", "invoice_date", "date", "inv_date", "tx_date"])
    col_gross = match_header_column(cols, ["gross_amount", "gross", "total_amount", "total", "amount", "total_due"])
    col_vat = match_header_column(cols, ["vat_amount", "vat", "tax_amount", "tax"])
    col_net = match_header_column(cols, ["net_amount", "net", "subtotal", "sub_total"])
    col_curr = match_header_column(cols, ["currency", "curr"])
    col_buyer = match_header_column(cols, ["buyer_name", "customer_name", "client_name", "customer"])
    col_buyer_tin = match_header_column(cols, ["buyer_tin", "customer_tin", "client_tin"])
    col_status = match_header_column(cols, ["validity_status", "status", "valid", "is_valid", "fiscal_status"])

    parsed_lines = []
    for idx, row in df.iterrows():
        supp_name = str(row[col_supp]).strip() if col_supp and row[col_supp] else ""
        if not supp_name or supp_name.lower() in ["total", "subtotal", "grand total"]:
            continue

        raw_tin = str(row[col_tin]).strip() if col_tin and row[col_tin] else ""
        raw_inv = str(row[col_inv]).strip() if col_inv and row[col_inv] else f"ZIMRA-INV-{idx + 1}"
        inv_date = parse_date_value(row[col_date]) if col_date else date.today()

        gross_minor = parse_amount_minor(row[col_gross]) if col_gross else 0
        vat_minor = parse_amount_minor(row[col_vat]) if col_vat else 0
        net_minor = parse_amount_minor(row[col_net]) if col_net else 0

        if gross_minor and not vat_minor and not net_minor:
            vat_minor = int(round(gross_minor * 0.155 / 1.155)) if inv_date >= date(2026, 1, 1) else int(round(gross_minor * 0.150 / 1.150))
            net_minor = gross_minor - vat_minor
        elif net_minor and not gross_minor:
            vat_minor = int(round(net_minor * 0.155)) if inv_date >= date(2026, 1, 1) else int(round(net_minor * 0.150))
            gross_minor = net_minor + vat_minor
        elif gross_minor and net_minor and not vat_minor:
            vat_minor = gross_minor - net_minor

        curr = default_currency
        if col_curr and row[col_curr]:
            curr_str = str(row[col_curr]).strip().upper()
            if "ZWG" in curr_str or "ZIG" in curr_str:
                curr = "ZWG"
            elif "USD" in curr_str:
                curr = "USD"

        buyer_name = str(row[col_buyer]).strip() if col_buyer and row[col_buyer] else (client_name or "")
        buyer_tin = str(row[col_buyer_tin]).strip() if col_buyer_tin and row[col_buyer_tin] else (client_tin or "")

        # Validity check in official ZIMRA report
        is_valid = True
        status_raw = "VALID"
        if col_status and row[col_status]:
            st = str(row[col_status]).strip().upper()
            status_raw = st
            if any(k in st for k in ["INVALID", "CANCEL", "VOID", "REJECT", "FAIL", "FALSE", "0"]):
                is_valid = False

        parsed_lines.append({
            "source_row_number": idx + 1,
            "supplier_name_raw": supp_name,
            "supplier_name_norm": normalise_supplier_name(supp_name)[0],
            "supplier_tin_raw": raw_tin or None,
            "supplier_tin_norm": normalise_tin(raw_tin) if raw_tin else None,
            "invoice_number_raw": raw_inv,
            "invoice_number_norm": normalise_invoice_number(raw_inv),
            "invoice_date": inv_date,
            "currency": curr,
            "net_minor": net_minor,
            "vat_minor": vat_minor,
            "gross_minor": gross_minor,
            "buyer_name_raw": buyer_name or None,
            "buyer_tin_raw": buyer_tin or None,
            "buyer_tin_norm": normalise_tin(buyer_tin) if buyer_tin else None,
            "validity_is_valid": is_valid,
            "validity_status_raw": status_raw,
        })

    return parsed_lines
