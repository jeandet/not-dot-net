from datetime import date, timedelta

from not_dot_net.backend.booking_service import MIN_BOOKING_LEAD_DAYS
from not_dot_net.frontend.bookings import (
    _default_booking_range,
    _minimum_booking_start,
    _normalize_booking_range,
    _qdate_option_date,
    _truncate_booking_owner,
)


def test_minimum_booking_start_is_seven_days_after_today():
    today = date(2026, 5, 26)

    assert _minimum_booking_start(today) == today + timedelta(days=MIN_BOOKING_LEAD_DAYS)


def test_default_booking_range_starts_at_minimum_date():
    today = date(2026, 5, 26)
    start = today + timedelta(days=MIN_BOOKING_LEAD_DAYS)

    assert _default_booking_range(today) == {
        "from": str(start),
        "to": str(start + timedelta(days=7)),
    }


def test_normalize_booking_range_keeps_valid_range():
    today = date(2026, 5, 26)
    value = {"from": "2026-06-02", "to": "2026-06-09"}

    assert _normalize_booking_range(value, today) == value


def test_normalize_booking_range_shifts_too_early_range_to_minimum_date():
    today = date(2026, 5, 26)

    assert _normalize_booking_range(
        {"from": "2026-05-26", "to": "2026-06-02"},
        today,
    ) == {"from": "2026-06-02", "to": "2026-06-09"}


def test_normalize_booking_range_falls_back_on_invalid_value():
    today = date(2026, 5, 26)

    assert _normalize_booking_range({"from": "bad"}, today) == _default_booking_range(today)


def test_qdate_option_date_uses_quasar_date_format():
    assert _qdate_option_date(date(2026, 6, 2)) == "2026/06/02"


def test_truncate_booking_owner_limits_display_name():
    assert _truncate_booking_owner("short@test.com") == "short@test.com"
    assert _truncate_booking_owner("lucas.bazin@lpp.polytechnique.fr") == (
        "lucas.bazin@lpp.polytech..."
    )
