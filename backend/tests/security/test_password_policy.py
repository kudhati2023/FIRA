import pytest
from fira.security.password_policy import (
    validate_password_complexity,
    calculate_entropy,
    MIN_PASSWORD_LENGTH,
)

def test_valid_enterprise_password():
    valid_passwords = [
        "Correct-Horse-Battery-Staple-2026!",
        "SecureP@ssw0rd!#2026Enterprise",
        "ZimraTaxRecovery#2026$",
        "Complex!P@ssw0rdForAdmin99",
    ]
    for pwd in valid_passwords:
        is_valid, errors = validate_password_complexity(pwd)
        assert is_valid, f"Expected '{pwd}' to be valid, errors: {errors}"
        assert len(errors) == 0

def test_password_too_short():
    short_pwd = "P@ss1!"  # 6 chars < 12
    is_valid, errors = validate_password_complexity(short_pwd)
    assert not is_valid
    assert any("at least 12 characters" in err for err in errors)

def test_password_missing_character_classes():
    # Missing uppercase
    is_valid, errors = validate_password_complexity("alllowercase12345!#")
    assert not is_valid
    assert any("uppercase" in err for err in errors)

    # Missing lowercase
    is_valid, errors = validate_password_complexity("ALLUPPERCASE12345!#")
    assert not is_valid
    assert any("lowercase" in err for err in errors)

    # Missing digit
    is_valid, errors = validate_password_complexity("NoDigitsInThisPassword!#")
    assert not is_valid
    assert any("digit" in err for err in errors)

    # Missing special character
    is_valid, errors = validate_password_complexity("NoSpecialCharacters12345")
    assert not is_valid
    assert any("special character" in err for err in errors)

def test_disallowed_common_passwords():
    common = [
        "password1234",
        "welcome12345",
        "123456789012",
        "fira_password_secure_123",
    ]
    for pwd in common:
        is_valid, errors = validate_password_complexity(pwd)
        assert not is_valid
        assert any("too common" in err for err in errors)

def test_repetitive_characters_rejected():
    repetitive = "AAAAAA123456!a"
    is_valid, errors = validate_password_complexity(repetitive)
    assert not is_valid
    assert any("5 or more identical" in err for err in errors)

def test_entropy_calculation():
    assert calculate_entropy("") == 0.0
    entropy_weak = calculate_entropy("aaaaaaaaaaaa")
    entropy_strong = calculate_entropy("V@l1d_Ent3rpr!se_P@ss#2026")
    assert entropy_strong > entropy_weak
    assert entropy_strong > 36.0
