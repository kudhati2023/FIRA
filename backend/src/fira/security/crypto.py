import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import List, Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from fira.config import settings

# 1. Enterprise Argon2id Password Hasher (RFC 9106 Parameters)
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

def hash_password(password: str) -> str:
    """Hash password using Argon2id with RFC 9106 parameters."""
    return _ph.hash(password)

def verify_password(hashed_password: str, password: str) -> bool:
    """Verify password against Argon2id hash with constant-time protection."""
    try:
        return _ph.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False

def password_needs_rehash(hashed_password: str) -> bool:
    """Check if hash needs updating to newer parameters."""
    try:
        return _ph.check_needs_rehash(hashed_password)
    except Exception:
        return True


# 2. Authenticated Symmetric Field Encryption (Fernet / AES-CBC + HMAC)
def _get_fernet_key(raw_key: str) -> bytes:
    """Derive 32-byte URL-safe base64 key suitable for Fernet."""
    # Ensure key is derived deterministically from secret
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt_secret(plaintext: str, key: Optional[str] = None) -> str:
    """Encrypt sensitive field at rest using authenticated symmetric encryption."""
    encryption_key = key or settings.MFA_ENCRYPTION_KEY
    fernet = Fernet(_get_fernet_key(encryption_key))
    encrypted = fernet.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")

def decrypt_secret(ciphertext: str, key: Optional[str] = None) -> str:
    """Decrypt sensitive field at rest."""
    encryption_key = key or settings.MFA_ENCRYPTION_KEY
    fernet = Fernet(_get_fernet_key(encryption_key))
    decrypted = fernet.decrypt(ciphertext.encode("utf-8"))
    return decrypted.decode("utf-8")


# 3. RFC 6238 TOTP Multi-Factor Authentication Engine
def generate_totp_secret() -> str:
    """Generate 160-bit cryptographically secure random base32 TOTP secret."""
    random_bytes = secrets.token_bytes(20)
    return base64.b32encode(random_bytes).decode("ascii").rstrip("=")

def generate_backup_codes(count: int = 8) -> List[str]:
    """Generate cryptographically secure single-use backup recovery codes."""
    return [secrets.token_hex(4).upper() + "-" + secrets.token_hex(4).upper() for _ in range(count)]

def _totp_code_at_counter(key_bytes: bytes, counter: int, digits: int = 6) -> str:
    """Compute HMAC-SHA1 code at specified counter according to RFC 6238/RFC 4226."""
    counter_bytes = struct.pack(">Q", counter)
    h = hmac.new(key_bytes, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    code_str = str(code_int % (10 ** digits))
    return code_str.zfill(digits)

def compute_totp(secret: str, for_time: Optional[float] = None, interval: int = 30) -> str:
    """Compute current 6-digit TOTP code for given base32 secret."""
    padded_secret = secret + "=" * ((8 - len(secret) % 8) % 8)
    key_bytes = base64.b32decode(padded_secret.upper())
    t = for_time if for_time is not None else time.time()
    counter = int(t // interval)
    return _totp_code_at_counter(key_bytes, counter)

def verify_totp_code(secret: str, code: str, window: int = 1, interval: int = 30) -> bool:
    """
    Verify 6-digit TOTP code with clock-drift tolerance window.
    window=1 checks [t - 1, t, t + 1] intervals (±30 seconds drift).
    """
    cleaned_code = code.strip().replace(" ", "")
    if len(cleaned_code) != 6 or not cleaned_code.isdigit():
        return False

    try:
        padded_secret = secret + "=" * ((8 - len(secret) % 8) % 8)
        key_bytes = base64.b32decode(padded_secret.upper())
    except Exception:
        return False

    current_counter = int(time.time() // interval)
    for offset in range(-window, window + 1):
        expected_code = _totp_code_at_counter(key_bytes, current_counter + offset)
        if hmac.compare_digest(expected_code, cleaned_code):
            return True
    return False

def get_totp_uri(secret: str, user_email: str, issuer: str = "FIRA") -> str:
    """Generate otpauth:// URI for authenticator applications."""
    from urllib.parse import quote
    encoded_issuer = quote(issuer)
    encoded_email = quote(user_email)
    return f"otpauth://totp/{encoded_issuer}:{encoded_email}?secret={secret}&issuer={encoded_issuer}&algorithm=SHA1&digits=6&period=30"


# 4. Tamper-Evident Audit Checksumming
def compute_audit_hash(
    tenant_id: Optional[str],
    actor_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    timestamp_iso: str,
    before_state: Optional[str] = None,
    after_state: Optional[str] = None,
    prev_hash: Optional[str] = None
) -> str:
    """
    Compute cryptographic SHA-256 digest of audit log event.
    Provides non-repudiation and tamper-evident audit chaining.
    """
    payload = f"{tenant_id or ''}|{actor_id or ''}|{action}|{entity_type}|{entity_id or ''}|{timestamp_iso}|{before_state or ''}|{after_state or ''}|{prev_hash or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
