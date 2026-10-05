import math
import re
from typing import List, Tuple

# NIST SP 800-63B Disallowed / Common Breached Passwords
COMMON_PASSWORDS = {
    "password", "password123", "password1234", "123456789012", "qwertyuiop12",
    "welcome12345", "admin1234567", "administrator", "iloveyou1234",
    "fira_password_secure_123", "changeme12345", "letmein12345",
    "supersecret12", "passphrase123", "company123456", "zimra1234567"
}

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
MIN_ENTROPY_BITS = 36.0

def calculate_entropy(password: str) -> float:
    """Calculate Shannon entropy bits for password character distribution."""
    if not password:
        return 0.0
    charset_size = 0
    if any(c.islower() for c in password):
        charset_size += 26
    if any(c.isupper() for c in password):
        charset_size += 26
    if any(c.isdigit() for c in password):
        charset_size += 10
    if any(not c.isalnum() for c in password):
        charset_size += 33

    if charset_size == 0:
        return 0.0
    return len(password) * math.log2(charset_size)

def validate_password_complexity(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password against NIST SP 800-63B Enterprise Standards.
    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must not exceed {MAX_PASSWORD_LENGTH} characters.")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one numerical digit.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+[\]\\/`~]", password):
        errors.append("Password must contain at least one special character.")

    # Check against known breached / dictionary passwords
    clean_lower = password.strip().lower()
    if clean_lower in COMMON_PASSWORDS:
        errors.append("Password is too common or appears in compromised password lists.")

    # Check for simple repeated characters (e.g. 'AAAAAA' or '111111')
    if re.search(r"(.)\1{4,}", password):
        errors.append("Password must not contain sequences of 5 or more identical characters.")

    # Check entropy
    if calculate_entropy(password) < MIN_ENTROPY_BITS:
        errors.append("Password does not have sufficient cryptographic randomness/entropy.")

    return (len(errors) == 0, errors)
