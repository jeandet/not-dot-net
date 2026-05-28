"""Tests for booking service — resource CRUD and reservation management."""

import pytest
import uuid
from datetime import date, timedelta

from not_dot_net.backend.booking_service import (
    BookingConflictError,
    BookingValidationError,
    cancel_booking,
    create_booking,
    create_resource,
    delete_resource,
    get_resource_by_id,
    list_bookings_for_resource,
    list_bookings_for_user,
    list_resources,
    update_resource,
)
from not_dot_net.backend.booking_models import Booking, Resource
from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.roles import RoleDefinition, roles_config
from not_dot_net.config import BookingsConfig, bookings_config

def _valid_start(extra_days: int = 0) -> date:
    return date.today() + timedelta(days=BookingsConfig().minimum_lead_days + extra_days)


async def _setup_roles():
    cfg = await roles_config.get()
    cfg.roles["admin"] = RoleDefinition(
        label="Admin",
        permissions=["manage_bookings", "manage_roles", "manage_settings"],
    )
    cfg.roles["staff"] = RoleDefinition(
        label="Staff",
        permissions=["create_workflows"],
    )
    await roles_config.set(cfg)


async def _create_user(email="user@test.com", role="staff") -> User:
    async with session_scope() as session:
        user = User(id=uuid.uuid4(), email=email, hashed_password="x", role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_test_resource(**kwargs) -> Resource:
    defaults = {"name": "Test PC", "resource_type": "desktop", "location": "Palaiseau"}
    defaults.update(kwargs)
    return await create_resource(**defaults)


# --- Resource CRUD ---


async def test_create_and_list_resources():
    await _create_test_resource(name="PC-01")
    await _create_test_resource(name="PC-02")
    resources = await list_resources()
    assert len(resources) == 2
    assert {r.name for r in resources} == {"PC-01", "PC-02"}


async def test_list_resources_active_only():
    r = await _create_test_resource()
    await update_resource(r.id, active=False)
    assert len(await list_resources(active_only=True)) == 0
    assert len(await list_resources(active_only=False)) == 1


async def test_update_resource():
    r = await _create_test_resource()
    updated = await update_resource(r.id, name="New Name", location="Jussieu")
    assert updated.name == "New Name"
    assert updated.location == "Jussieu"


async def test_update_nonexistent_resource():
    with pytest.raises(ValueError, match="not found"):
        await update_resource(uuid.uuid4(), name="X")


async def test_update_resource_rejects_immutable_fields():
    r = await _create_test_resource()
    with pytest.raises(ValueError, match="Cannot update field"):
        await update_resource(r.id, id=uuid.uuid4())
    with pytest.raises(ValueError, match="Cannot update field"):
        await update_resource(r.id, created_at=date.today())


async def test_delete_resource():
    r = await _create_test_resource()
    await delete_resource(r.id)
    assert await get_resource_by_id(r.id) is None


async def test_delete_nonexistent_resource():
    with pytest.raises(ValueError, match="not found"):
        await delete_resource(uuid.uuid4())


async def test_get_resource_by_id():
    r = await _create_test_resource()
    found = await get_resource_by_id(r.id)
    assert found is not None
    assert found.name == r.name


async def test_get_resource_by_id_not_found():
    assert await get_resource_by_id(uuid.uuid4()) is None


# --- Booking validation ---


async def test_create_booking_success():
    user = await _create_user()
    r = await _create_test_resource()
    tomorrow = _valid_start()
    end = tomorrow + timedelta(days=3)
    b = await create_booking(r.id, user.id, tomorrow, end, note="Test")
    assert b.resource_id == r.id
    assert b.start_date == tomorrow
    assert b.end_date == end


async def test_create_booking_rejects_missing_resource():
    user = await _create_user()
    tomorrow = _valid_start()
    with pytest.raises(ValueError, match="not found"):
        await create_booking(uuid.uuid4(), user.id, tomorrow, tomorrow + timedelta(days=1))


async def test_create_booking_rejects_inactive_resource():
    user = await _create_user()
    r = await _create_test_resource()
    r = await update_resource(r.id, active=False)
    tomorrow = _valid_start()
    with pytest.raises(BookingValidationError, match="not active"):
        await create_booking(r.id, user.id, tomorrow, tomorrow + timedelta(days=1))


async def test_booking_end_before_start():
    user = await _create_user()
    r = await _create_test_resource()
    tomorrow = _valid_start()
    with pytest.raises(BookingValidationError, match="End date"):
        await create_booking(r.id, user.id, tomorrow, tomorrow)


async def test_booking_in_the_past():
    user = await _create_user()
    r = await _create_test_resource()
    yesterday = date.today() - timedelta(days=1)
    with pytest.raises(BookingValidationError, match="past"):
        await create_booking(r.id, user.id, yesterday, date.today() + timedelta(days=1))


async def test_booking_requires_seven_days_notice():
    user = await _create_user()
    r = await _create_test_resource()
    start = date.today() + timedelta(days=6)
    with pytest.raises(BookingValidationError, match="at least 7 days"):
        await create_booking(r.id, user.id, start, start + timedelta(days=3))


async def test_booking_minimum_lead_days_uses_bookings_config():
    user = await _create_user()
    r = await _create_test_resource()
    await bookings_config.set(BookingsConfig(minimum_lead_days=3))
    try:
        start = date.today() + timedelta(days=2)
        with pytest.raises(BookingValidationError, match="at least 3 days"):
            await create_booking(r.id, user.id, start, start + timedelta(days=3))
        booking = await create_booking(
            r.id,
            user.id,
            date.today() + timedelta(days=3),
            date.today() + timedelta(days=6),
        )
    finally:
        await bookings_config.reset()

    assert booking.start_date == date.today() + timedelta(days=3)


async def test_booking_exceeds_max_days():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    end = start + timedelta(days=200)
    with pytest.raises(BookingValidationError, match="exceed"):
        await create_booking(r.id, user.id, start, end)


async def test_booking_max_days_uses_bookings_config():
    user = await _create_user()
    r = await _create_test_resource()
    await bookings_config.set(BookingsConfig(max_booking_days=4))
    try:
        start = _valid_start()
        with pytest.raises(BookingValidationError, match="exceed 4 days"):
            await create_booking(r.id, user.id, start, start + timedelta(days=5))
        booking = await create_booking(r.id, user.id, start, start + timedelta(days=4))
    finally:
        await bookings_config.reset()

    assert booking.end_date == start + timedelta(days=4)


# --- Booking conflicts ---


async def test_booking_conflict():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    end = start + timedelta(days=5)
    await create_booking(r.id, user.id, start, end)

    user2 = await _create_user(email="user2@test.com")
    overlap_start = start + timedelta(days=2)
    overlap_end = end + timedelta(days=2)
    with pytest.raises(BookingConflictError):
        await create_booking(r.id, user2.id, overlap_start, overlap_end)


async def test_booking_rejects_adjacent_booking_without_setup_buffer():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    mid = start + timedelta(days=5)
    end = mid + timedelta(days=5)
    await create_booking(r.id, user.id, start, mid)
    with pytest.raises(BookingConflictError, match="setup buffer"):
        await create_booking(r.id, user.id, mid, end)


async def test_booking_allows_after_resource_setup_buffer():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    first_end = start + timedelta(days=5)
    second_start = first_end + timedelta(days=7)
    await create_booking(r.id, user.id, start, first_end)
    b2 = await create_booking(r.id, user.id, second_start, second_start + timedelta(days=5))
    assert b2.start_date == second_start


async def test_booking_setup_buffer_uses_bookings_config():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    first_end = start + timedelta(days=5)
    await bookings_config.set(BookingsConfig(resource_setup_buffer_days=2))
    try:
        await create_booking(r.id, user.id, start, first_end)
        with pytest.raises(BookingConflictError, match="2-day setup buffer"):
            await create_booking(
                r.id,
                user.id,
                first_end + timedelta(days=1),
                first_end + timedelta(days=3),
            )
        b2 = await create_booking(
            r.id,
            user.id,
            first_end + timedelta(days=2),
            first_end + timedelta(days=4),
        )
    finally:
        await bookings_config.reset()

    assert b2.start_date == first_end + timedelta(days=2)


async def test_booking_setup_buffer_is_per_resource():
    user = await _create_user()
    r1 = await _create_test_resource(name="PC-01")
    r2 = await _create_test_resource(name="PC-02")
    start = _valid_start()
    end = start + timedelta(days=5)
    await create_booking(r1.id, user.id, start, end)
    b2 = await create_booking(r2.id, user.id, start + timedelta(days=1), end + timedelta(days=1))
    assert b2.resource_id == r2.id


# --- Booking listing ---


async def test_list_bookings_for_resource():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    end = start + timedelta(days=3)
    await create_booking(r.id, user.id, start, end)
    bookings = await list_bookings_for_resource(r.id)
    assert len(bookings) == 1


async def test_list_bookings_for_user():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    end = start + timedelta(days=3)
    await create_booking(r.id, user.id, start, end)
    bookings = await list_bookings_for_user(user.id)
    assert len(bookings) == 1


# --- Booking cancellation ---


async def test_cancel_own_booking():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    end = start + timedelta(days=3)
    b = await create_booking(r.id, user.id, start, end)
    await cancel_booking(b.id, user.id)
    assert len(await list_bookings_for_resource(r.id)) == 0


async def test_cancel_other_user_booking_rejected():
    user1 = await _create_user(email="u1@test.com")
    user2 = await _create_user(email="u2@test.com")
    r = await _create_test_resource()
    start = _valid_start()
    b = await create_booking(r.id, user1.id, start, start + timedelta(days=3))
    with pytest.raises(PermissionError):
        await cancel_booking(b.id, user2.id)


async def test_cancel_as_admin():
    user1 = await _create_user(email="u1@test.com")
    admin = await _create_user(email="admin@test.com", role="admin")
    r = await _create_test_resource()
    start = _valid_start()
    b = await create_booking(r.id, user1.id, start, start + timedelta(days=3))
    await cancel_booking(b.id, admin.id, is_admin=True)
    assert len(await list_bookings_for_resource(r.id)) == 0


async def test_cancel_nonexistent_booking():
    user = await _create_user()
    with pytest.raises(ValueError, match="not found"):
        await cancel_booking(uuid.uuid4(), user.id)


# --- OS/software ---


async def test_booking_with_os_and_software():
    user = await _create_user()
    r = await _create_test_resource()
    start = _valid_start()
    b = await create_booking(
        r.id, user.id, start, start + timedelta(days=3),
        os_choice="Ubuntu", software_tags=["Python", "GCC"],
    )
    assert b.os_choice == "Ubuntu"
    assert b.software_tags == ["Python", "GCC"]


async def test_create_booking_actor_can_only_book_for_self():
    await _setup_roles()
    user1 = await _create_user(email="u1@test.com", role="staff")
    user2 = await _create_user(email="u2@test.com", role="staff")
    r = await _create_test_resource()
    start = _valid_start()

    with pytest.raises(PermissionError):
        await create_booking(
            r.id,
            user2.id,
            start,
            start + timedelta(days=3),
            actor=user1,
        )


async def test_create_booking_actor_manager_can_book_for_other_user():
    await _setup_roles()
    admin = await _create_user(email="admin-book@test.com", role="admin")
    user = await _create_user(email="user-book@test.com", role="staff")
    r = await _create_test_resource()
    start = _valid_start()

    booking = await create_booking(
        r.id,
        user.id,
        start,
        start + timedelta(days=3),
        actor=admin,
    )

    assert booking.user_id == user.id


# --- Permission enforcement ---


async def test_create_resource_requires_permission():
    await _setup_roles()
    staff = await _create_user(email="staff@test.com", role="staff")
    with pytest.raises(PermissionError):
        await create_resource("PC", "desktop", actor=staff)


async def test_create_resource_allowed_with_permission():
    await _setup_roles()
    admin = await _create_user(email="admin@test.com", role="admin")
    r = await create_resource("PC", "desktop", actor=admin)
    assert r.name == "PC"


async def test_update_resource_requires_permission():
    await _setup_roles()
    admin = await _create_user(email="admin@test.com", role="admin")
    r = await create_resource("PC", "desktop", actor=admin)
    staff = await _create_user(email="staff@test.com", role="staff")
    with pytest.raises(PermissionError):
        await update_resource(r.id, actor=staff, name="New")


async def test_delete_resource_requires_permission():
    await _setup_roles()
    admin = await _create_user(email="admin@test.com", role="admin")
    r = await create_resource("PC", "desktop", actor=admin)
    staff = await _create_user(email="staff@test.com", role="staff")
    with pytest.raises(PermissionError):
        await delete_resource(r.id, actor=staff)


async def test_cancel_booking_with_actor_admin():
    await _setup_roles()
    admin = await _create_user(email="admin@test.com", role="admin")
    user1 = await _create_user(email="u1@test.com", role="staff")
    r = await create_resource("PC", "desktop", actor=admin)
    start = _valid_start()
    b = await create_booking(r.id, user1.id, start, start + timedelta(days=3))
    await cancel_booking(b.id, actor=admin)
    assert len(await list_bookings_for_resource(r.id)) == 0


async def test_cancel_booking_non_owner_non_admin_rejected():
    await _setup_roles()
    admin = await _create_user(email="admin@test.com", role="admin")
    user1 = await _create_user(email="u1@test.com", role="staff")
    user2 = await _create_user(email="u2@test.com", role="staff")
    r = await create_resource("PC", "desktop", actor=admin)
    start = _valid_start()
    b = await create_booking(r.id, user1.id, start, start + timedelta(days=3))
    with pytest.raises(PermissionError):
        await cancel_booking(b.id, actor=user2)
