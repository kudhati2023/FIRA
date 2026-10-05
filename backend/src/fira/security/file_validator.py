import os
import re
import uuid
from typing import BinaryIO, Tuple
from fastapi import HTTPException, status
from fira.config import settings

# Allowed file extensions for tax and ledger ingestion (HC-2)
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# Magic byte signatures
MAGIC_SIGNATURES = {
    # XLSX (ZIP file header: PK\x03\x04)
    "xlsx": b"\x50\x4b\x03\x04",
    # Legacy XLS (Compound Binary Format: \xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1)
    "xls": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
}

import posixpath

def sanitize_filename(filename: str) -> str:
    """
    Sanitize uploaded filename to prevent Directory Traversal (CWE-22)
    and arbitrary command/path injection. Cross-platform safe for POSIX and Windows.
    """
    # Normalize backslashes to forward slashes and extract basename
    normalized = filename.replace("\\", "/")
    base_name = posixpath.basename(normalized)
    # Remove null bytes, control characters, and unsafe chars
    clean_name = re.sub(r"[^\w\s\.-]", "", base_name).strip()
    # Prevent hidden files or relative path tricks
    if clean_name.startswith("."):
        clean_name = "upload_" + clean_name.lstrip(".")
    if not clean_name:
        clean_name = f"upload_{uuid.uuid4().hex[:8]}"
    return clean_name

def generate_safe_storage_key(tenant_id: uuid.UUID, engagement_id: uuid.UUID, sanitized_filename: str) -> str:
    """Generate isolated, non-colliding storage path in object storage."""
    file_id = uuid.uuid4()
    _, ext = os.path.splitext(sanitized_filename)
    return f"tenants/{tenant_id}/engagements/{engagement_id}/{file_id}{ext.lower()}"

def validate_uploaded_file(
    filename: str,
    file_stream: BinaryIO,
    max_size: int = settings.MAX_UPLOAD_SIZE_BYTES
) -> Tuple[str, str]:
    """
    Verify file extension, size limit, and binary magic bytes to prevent
    polyglot files, webshells, or executable disguise attacks.
    Returns (sanitized_filename, validated_extension).
    """
    clean_name = sanitize_filename(filename)
    _, ext = os.path.splitext(clean_name)
    ext_lower = ext.lower()

    if ext_lower not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext_lower}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Read leading bytes for magic byte validation
    header_bytes = file_stream.read(8)
    file_stream.seek(0, os.SEEK_END)
    file_size = file_stream.tell()
    file_stream.seek(0)

    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {max_mb:.1f} MB"
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File cannot be empty"
        )

    # Verify magic bytes
    if ext_lower == ".xlsx":
        if not header_bytes.startswith(MAGIC_SIGNATURES["xlsx"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security Error: File content does not match genuine XLSX archive signature."
            )
    elif ext_lower == ".xls":
        if not header_bytes.startswith(MAGIC_SIGNATURES["xls"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security Error: File content does not match genuine XLS binary signature."
            )
    elif ext_lower == ".csv":
        # Disallow executable headers in CSV (e.g. Windows PE "MZ" or Linux ELF)
        if header_bytes.startswith(b"MZ") or header_bytes.startswith(b"\x7fELF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security Error: Executable disguised as CSV detected."
            )
        # Disallow null bytes in CSV
        sample = file_stream.read(min(file_size, 4096))
        file_stream.seek(0)
        if b"\x00" in sample:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security Error: Binary characters detected in text CSV export."
            )

    return (clean_name, ext_lower)
