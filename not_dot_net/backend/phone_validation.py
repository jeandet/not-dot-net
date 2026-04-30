"""Phone number validation + E.164 normalization via Google's libphonenumber.

Default region is "FR" (lab is in France). Numbers entered with an explicit
country code (`+44 ...`) parse correctly regardless of the default region.
"""

import phonenumbers


DEFAULT_REGION = "FR"


def is_valid_phone(value: str, region: str = DEFAULT_REGION) -> bool:
    """Return True if `value` parses as a valid phone number for `region`."""
    if not value:
        return False
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException:
        return False
    return phonenumbers.is_valid_number(parsed)


def format_phone_e164(value: str, region: str = DEFAULT_REGION) -> str:
    """Return `value` normalized to E.164 (e.g. "+33612345678").

    Raises ValueError if the input is not a valid phone number.
    """
    if not value:
        raise ValueError("Phone number is empty")
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as e:
        raise ValueError(f"Could not parse phone number: {e}") from e
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number: {value!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
