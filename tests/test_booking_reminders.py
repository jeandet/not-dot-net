from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
import uuid

from sqlalchemy import select

from not_dot_net.backend.booking_models import Booking, Resource
from not_dot_net.backend.booking_service import (
    render_booking_reminder_body,
    send_booking_end_reminders,
)
from not_dot_net.backend.db import User, session_scope
from not_dot_net.config import BookingsConfig, bookings_config


async def _create_user(email="user@test.com", full_name="Test User", active=True) -> User:
    async with session_scope() as session:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password="x",
            full_name=full_name,
            is_active=active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_resource(name="Reminder PC") -> Resource:
    async with session_scope() as session:
        resource = Resource(name=name, resource_type="desktop", location="Palaiseau")
        session.add(resource)
        await session.commit()
        await session.refresh(resource)
        return resource


async def _create_booking(user, resource, *, end_offset_days: int) -> Booking:
    today = date(2026, 5, 26)
    async with session_scope() as session:
        booking = Booking(
            user_id=user.id,
            resource_id=resource.id,
            start_date=today - timedelta(days=3),
            end_date=today + timedelta(days=end_offset_days),
            os_choice="Ubuntu",
            software_tags=["Python", "GCC"],
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return booking


def test_render_booking_reminder_body_escapes_user_content():
    user = User(
        id=uuid.uuid4(),
        email="x@test.com",
        hashed_password="x",
        full_name="<script>",
    )
    resource = Resource(name="<PC>", resource_type="desktop")
    booking = Booking(
        user_id=user.id,
        resource_id=resource.id,
        start_date=date(2026, 5, 20),
        end_date=date(2026, 5, 27),
        os_choice="<Ubuntu>",
        software_tags=["A&B"],
    )

    body = render_booking_reminder_body(user=user, booking=booking, resource=resource)

    assert "&lt;script&gt;" in body
    assert "&lt;PC&gt;" in body
    assert "&lt;Ubuntu&gt;" in body
    assert "A&amp;B" in body


async def test_send_booking_end_reminders_queues_mail_and_marks_booking():
    user = await _create_user()
    resource = await _create_resource()
    booking = await _create_booking(user, resource, end_offset_days=1)

    with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
        queued = await send_booking_end_reminders(today=date(2026, 5, 26))

    assert queued == 1
    send.assert_awaited_once()
    assert send.await_args.args[0] == user.email
    assert "booking is ending soon" in send.await_args.args[1]

    async with session_scope() as session:
        stored = await session.get(Booking, booking.id)
        assert stored.reminder_sent_at is not None


async def test_send_booking_end_reminders_does_not_send_twice():
    user = await _create_user()
    resource = await _create_resource()
    await _create_booking(user, resource, end_offset_days=1)

    with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock):
        assert await send_booking_end_reminders(today=date(2026, 5, 26)) == 1

    with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
        assert await send_booking_end_reminders(today=date(2026, 5, 26)) == 0

    send.assert_not_awaited()


async def test_send_booking_end_reminders_ignores_later_bookings():
    user = await _create_user()
    resource = await _create_resource()
    await _create_booking(user, resource, end_offset_days=2)

    with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
        queued = await send_booking_end_reminders(today=date(2026, 5, 26))

    assert queued == 0
    send.assert_not_awaited()

    async with session_scope() as session:
        stored = (await session.execute(select(Booking))).scalar_one()
        assert stored.reminder_sent_at is None


async def test_send_booking_end_reminders_uses_configured_lead_days():
    user = await _create_user()
    resource = await _create_resource()
    await _create_booking(user, resource, end_offset_days=7)
    await bookings_config.set(BookingsConfig(reminder_lead_days=7))
    try:
        with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
            queued = await send_booking_end_reminders(today=date(2026, 5, 26))
    finally:
        await bookings_config.reset()

    assert queued == 1
    send.assert_awaited_once()


async def test_send_booking_end_reminders_can_be_disabled_with_empty_lead_days():
    user = await _create_user()
    resource = await _create_resource()
    await _create_booking(user, resource, end_offset_days=1)
    await bookings_config.set(BookingsConfig(reminder_lead_days=None))
    try:
        with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
            queued = await send_booking_end_reminders(today=date(2026, 5, 26))
    finally:
        await bookings_config.reset()

    assert queued == 0
    send.assert_not_awaited()


async def test_send_booking_end_reminders_zero_lead_days_sends_on_end_date():
    user = await _create_user()
    resource = await _create_resource()
    await _create_booking(user, resource, end_offset_days=0)
    await bookings_config.set(BookingsConfig(reminder_lead_days=0))
    try:
        with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
            queued = await send_booking_end_reminders(today=date(2026, 5, 26))
    finally:
        await bookings_config.reset()

    assert queued == 1
    send.assert_awaited_once()


async def test_send_booking_end_reminders_ignores_inactive_users():
    user = await _create_user(active=False)
    resource = await _create_resource()
    await _create_booking(user, resource, end_offset_days=1)

    with patch("not_dot_net.backend.booking_service.send_mail", new_callable=AsyncMock) as send:
        queued = await send_booking_end_reminders(today=date(2026, 5, 26))

    assert queued == 0
    send.assert_not_awaited()
