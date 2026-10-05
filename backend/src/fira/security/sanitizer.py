import re
from typing import Any, Dict, List, Union

SENSITIVE_KEY_PATTERNS = {
    "password", "password_hash", "new_password", "old_password",
    "secret", "mfa_secret", "mfa_secret_encrypted", "jwt_secret",
    "token", "access_token", "refresh_token", "authorization",
    "api_key", "cookie", "private_key", "encryption_key"
}

MASK_VALUE = "[REDACTED]"

def mask_auth_header(header_value: str) -> str:
    """Mask JWT or Bearer token in authorization header."""
    if not header_value:
        return ""
    if header_value.lower().startswith("bearer "):
        parts = header_value.split(" ", 1)
        if len(parts) == 2:
            token = parts[1]
            if len(token) > 10:
                return f"Bearer {token[:4]}...{token[-4:]}"
            return "Bearer [REDACTED]"
    return "[REDACTED]"

def sanitize_data(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and sensitive strings,
    ensuring PII, passwords, and cryptographic secrets are redacted from logs and audits.
    """
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEY_PATTERNS):
                sanitized[key] = MASK_VALUE
            elif isinstance(value, (dict, list)):
                sanitized[key] = sanitize_data(value)
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        # Look for Bearer tokens embedded in string
        if "Bearer " in data:
            return re.sub(r"Bearer\s+[A-Za-z0-9-_=.]+", "Bearer [REDACTED]", data)
        return data
    return data
