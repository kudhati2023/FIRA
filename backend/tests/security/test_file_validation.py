import io
import pytest
from fastapi import HTTPException
from fira.security.file_validator import (
    sanitize_filename,
    validate_uploaded_file,
    generate_safe_storage_key,
)
import uuid

def test_sanitize_filename():
    assert sanitize_filename("../../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("valid_invoice_export.xlsx") == "valid_invoice_export.xlsx"
    assert sanitize_filename(".hidden_file.csv") == "upload_hidden_file.csv"

def test_generate_safe_storage_key():
    tenant_id = uuid.uuid4()
    engagement_id = uuid.uuid4()
    key = generate_safe_storage_key(tenant_id, engagement_id, "export.xlsx")
    assert f"tenants/{tenant_id}/engagements/{engagement_id}/" in key
    assert key.endswith(".xlsx")

def test_validate_valid_xlsx():
    # Valid XLSX begins with ZIP signature: PK\x03\x04
    xlsx_stream = io.BytesIO(b"\x50\x4b\x03\x04\x14\x00\x06\x00DummyContentForZipArchive")
    name, ext = validate_uploaded_file("tax_records.xlsx", xlsx_stream)
    assert name == "tax_records.xlsx"
    assert ext == ".xlsx"

def test_validate_valid_xls():
    # Valid XLS begins with Compound Binary File signature
    xls_stream = io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1LegacyContent")
    name, ext = validate_uploaded_file("old_records.xls", xls_stream)
    assert ext == ".xls"

def test_validate_valid_csv():
    csv_stream = io.BytesIO(b"Date,Invoice,Amount,VAT\n2026-01-01,INV001,100.00,15.50\n")
    name, ext = validate_uploaded_file("claims.csv", csv_stream)
    assert ext == ".csv"

def test_reject_executable_disguised_as_csv():
    # Windows PE executable starts with 'MZ'
    fake_csv = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00MaliciousExecutableDisguisedAsCSV")
    with pytest.raises(HTTPException) as exc_info:
        validate_uploaded_file("claims.csv", fake_csv)
    assert exc_info.value.status_code == 400
    assert "Executable disguised as CSV" in exc_info.value.detail

def test_reject_null_bytes_in_csv():
    corrupt_csv = io.BytesIO(b"Date,Invoice\x00,Amount\n2026-01-01,INV01,100\n")
    with pytest.raises(HTTPException) as exc_info:
        validate_uploaded_file("claims.csv", corrupt_csv)
    assert exc_info.value.status_code == 400
    assert "Binary characters detected" in exc_info.value.detail

def test_reject_invalid_magic_bytes_xlsx():
    # File named .xlsx but contents is plain text or wrong magic bytes
    fake_xlsx = io.BytesIO(b"This is just a text file named xlsx")
    with pytest.raises(HTTPException) as exc_info:
        validate_uploaded_file("spoofed.xlsx", fake_xlsx)
    assert exc_info.value.status_code == 400
    assert "archive signature" in exc_info.value.detail

def test_reject_unsupported_extensions():
    stream = io.BytesIO(b"print('hello')")
    with pytest.raises(HTTPException) as exc_info:
        validate_uploaded_file("script.py", stream)
    assert exc_info.value.status_code == 400
    assert "Unsupported file type" in exc_info.value.detail

def test_reject_empty_file():
    empty_stream = io.BytesIO(b"")
    with pytest.raises(HTTPException) as exc_info:
        validate_uploaded_file("empty.csv", empty_stream)
    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()

def test_reject_oversized_file():
    big_stream = io.BytesIO(b"\x50\x4b\x03\x04" + b"X" * 1000)
    with pytest.raises(HTTPException) as exc_info:
        validate_uploaded_file("large.xlsx", big_stream, max_size=500)
    assert exc_info.value.status_code == 413
