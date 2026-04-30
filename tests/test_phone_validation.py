"""Tests for phone number validation + E.164 normalization."""

import pytest

from not_dot_net.backend.phone_validation import format_phone_e164, is_valid_phone


def test_valid_french_mobile_bare():
    assert is_valid_phone("0612345678") is True


def test_valid_french_mobile_with_country_code():
    assert is_valid_phone("+33612345678") is True


def test_valid_us_with_country_code_overrides_default():
    """A number with explicit + country code parses regardless of default region."""
    assert is_valid_phone("+1 415 555 0132") is True


def test_invalid_too_short():
    assert is_valid_phone("12345") is False


def test_invalid_garbage():
    assert is_valid_phone("not a phone number") is False


def test_empty_is_invalid():
    assert is_valid_phone("") is False


def test_format_e164_french_bare():
    assert format_phone_e164("06 12 34 56 78") == "+33612345678"


def test_format_e164_already_e164():
    assert format_phone_e164("+33612345678") == "+33612345678"


def test_format_e164_us_with_country_code():
    assert format_phone_e164("+1 415 555 0132") == "+14155550132"


def test_format_e164_invalid_raises():
    with pytest.raises(ValueError):
        format_phone_e164("12345")


def test_format_e164_garbage_raises():
    with pytest.raises(ValueError):
        format_phone_e164("not a phone number")


def test_default_region_can_be_overridden():
    """A bare US number with region='US' parses; with default 'FR' it would not."""
    assert is_valid_phone("415 555 0132", region="US") is True
    assert is_valid_phone("415 555 0132") is False
