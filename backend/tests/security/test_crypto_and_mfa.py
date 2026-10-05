import time
import pytest
from fira.security.crypto import (
    hash_password,
    verify_password,
    password_needs_rehash,
    encrypt_secret,
    decrypt_secret,
    generate_totp_secret,
    compute_totp,
    verify_totp_code,
    get_totp_uri,
    generate_backup_codes,
    compute_audit_hash,
)

def test_argon2id_hashing_and_verification():
    raw_pwd = "P@ssw0rdForTest#2026"
    pwd_hash = hash_password(raw_pwd)

    assert pwd_hash.startswith("$argon2id$")
    assert verify_password(pwd_hash, raw_pwd) is True
    assert verify_password(pwd_hash, "WrongPassword#123") is False
    assert password_needs_rehash(pwd_hash) is False

def test_fernet_symmetric_field_encryption():
    plaintext = "super_secret_taxpayer_api_token_12345"
    ciphertext = encrypt_secret(plaintext)

    assert ciphertext != plaintext
    decrypted = decrypt_secret(ciphertext)
    assert decrypted == plaintext

    # Tampered ciphertext fails decryption
    tampered = ciphertext[:-4] + "AAAA"
    with pytest.raises(Exception):
        decrypt_secret(tampered)

def test_totp_generation_and_verification():
    secret = generate_totp_secret()
    assert len(secret) >= 26

    current_code = compute_totp(secret)
    assert len(current_code) == 6
    assert current_code.isdigit()

    # Verification within window
    assert verify_totp_code(secret, current_code, window=1) is True

    # Invalid code rejected
    assert verify_totp_code(secret, "000000" if current_code != "000000" else "111111") is False

    # Invalid secret format rejected safely
    assert verify_totp_code("INVALID_SECRET_!!!", current_code) is False

def test_totp_uri_generation():
    secret = "JBSWY3DPEHPK3PXP"
    uri = get_totp_uri(secret, "user@example.com", issuer="FIRA Tax System")
    assert uri.startswith("otpauth://totp/")
    assert "secret=" + secret in uri
    assert "user%40example.com" in uri or "user@example.com" in uri

def test_backup_codes_generation():
    codes = generate_backup_codes(count=8)
    assert len(codes) == 8
    for code in codes:
        assert len(code) == 17  # 8-hex - 8-hex e.g. ABCD1234-EF567890
        assert "-" in code

def test_compute_audit_hash():
    h1 = compute_audit_hash(
        tenant_id="tenant-1",
        actor_id="user-1",
        action="UPDATE_CONFIG",
        entity_type="config_setting",
        entity_id="cfg-1",
        timestamp_iso="2026-09-06T12:00:00Z",
        before_state='{"rate": 1500}',
        after_state='{"rate": 1550}',
    )
    assert len(h1) == 64  # SHA-256 hex string

    # Any change produces a completely different hash (avalanche effect)
    h2 = compute_audit_hash(
        tenant_id="tenant-1",
        actor_id="user-1",
        action="UPDATE_CONFIG",
        entity_type="config_setting",
        entity_id="cfg-1",
        timestamp_iso="2026-09-06T12:00:00Z",
        before_state='{"rate": 1500}',
        after_state='{"rate": 1551}',  # slight change
    )
    assert h1 != h2
