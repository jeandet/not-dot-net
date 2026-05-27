"""Booking service — resource CRUD and reservation management."""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from not_dot_net.backend.booking_models import Booking, Resource
from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.mail import send_mail
from not_dot_net.backend.permissions import check_permission, has_permissions, permission
from not_dot_net.config import bookings_config, org_config

MANAGE_BOOKINGS = permission("manage_bookings", "Manage bookings", "Create/edit/delete resources and software")

logger = logging.getLogger("not_dot_net.booking_service")


class BookingConflictError(Exception):
    pass


class BookingValidationError(Exception):
    pass


# --- Resources ---


async def list_resources(active_only: bool = True) -> list[Resource]:
    async with session_scope() as session:
        query = select(Resource).order_by(Resource.name)
        if active_only:
            query = query.where(Resource.active == True)  # noqa: E712
        result = await session.execute(query)
        return list(result.scalars().all())


async def create_resource(name: str, resource_type: str, description: str = "",
                          location: str = "", specs: dict | None = None,
                          actor=None) -> Resource:
    if actor is not None:
        await check_permission(actor, MANAGE_BOOKINGS)
    async with session_scope() as session:
        resource = Resource(
            name=name,
            resource_type=resource_type,
            description=description or None,
            location=location or None,
            specs=specs,
        )
        session.add(resource)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError(f"Resource name '{name}' already exists") from exc
        await session.refresh(resource)

    from not_dot_net.backend.audit import log_audit
    await log_audit(
        "resource", "create",
        target_type="resource", target_id=resource.id,
        detail=f"name={name} type={resource_type}",
    )
    return resource


_RESOURCE_MUTABLE = frozenset({"name", "resource_type", "description", "location", "specs", "active"})


async def update_resource(resource_id: uuid.UUID, actor=None, **kwargs) -> Resource:
    if actor is not None:
        await check_permission(actor, MANAGE_BOOKINGS)
    async with session_scope() as session:
        resource = await session.get(Resource, resource_id)
        if resource is None:
            raise ValueError(f"Resource {resource_id} not found")
        for key, value in kwargs.items():
            if key not in _RESOURCE_MUTABLE:
                raise ValueError(f"Cannot update field '{key}'")
            setattr(resource, key, value)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("Resource update violates a uniqueness constraint") from exc
        await session.refresh(resource)
        return resource


async def delete_resource(resource_id: uuid.UUID, actor=None) -> None:
    if actor is not None:
        await check_permission(actor, MANAGE_BOOKINGS)
    async with session_scope() as session:
        resource = await session.get(Resource, resource_id)
        if resource is None:
            raise ValueError(f"Resource {resource_id} not found")
        await session.delete(resource)
        await session.commit()


# --- Bookings ---


async def list_bookings_for_resource(
    resource_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None,
) -> list[Booking]:
    async with session_scope() as session:
        query = (
            select(Booking)
            .where(Booking.resource_id == resource_id)
            .order_by(Booking.start_date)
        )
        if from_date:
            query = query.where(Booking.end_date >= from_date)
        if to_date:
            query = query.where(Booking.start_date <= to_date)
        result = await session.execute(query)
        return list(result.scalars().all())


async def list_bookings_for_user(user_id: uuid.UUID) -> list[Booking]:
    async with session_scope() as session:
        result = await session.execute(
            select(Booking)
            .where(Booking.user_id == user_id, Booking.end_date >= date.today())
            .order_by(Booking.start_date)
        )
        return list(result.scalars().all())


async def create_booking(
    resource_id: uuid.UUID, user_id: uuid.UUID,
    start_date: date, end_date: date, note: str = "",
    os_choice: str | None = None, software_tags: list[str] | None = None,
    actor=None,
) -> Booking:
    if actor is not None:
        is_manager = await has_permissions(actor, MANAGE_BOOKINGS)
        if user_id != actor.id and not is_manager:
            raise PermissionError("Can only create bookings for yourself")
    if start_date >= end_date:
        raise BookingValidationError("End date must be after start date")
    if start_date < date.today():
        raise BookingValidationError("Cannot book in the past")
    cfg = await bookings_config.get()
    minimum_lead_days = cfg.minimum_lead_days
    earliest_start = date.today() + timedelta(days=minimum_lead_days)
    if start_date < earliest_start:
        raise BookingValidationError(
            f"Bookings must start at least {minimum_lead_days} days from today"
        )
    max_booking_days = cfg.max_booking_days
    if (end_date - start_date).days > max_booking_days:
        raise BookingValidationError(f"Booking cannot exceed {max_booking_days} days")
    setup_buffer_days = cfg.resource_setup_buffer_days

    async with session_scope() as session:
        async with session.begin():
            resource = await session.get(Resource, resource_id)
            if resource is None:
                raise ValueError(f"Resource {resource_id} not found")
            if not resource.active:
                raise BookingValidationError("Resource is not active")

            # Lock overlapping rows to prevent concurrent double-booking.
            # with_for_update() is a no-op on SQLite but correct for PostgreSQL.
            conflicts = await session.execute(
                select(Booking).where(
                    Booking.resource_id == resource_id,
                    Booking.start_date < end_date + timedelta(days=setup_buffer_days),
                    Booking.end_date > start_date - timedelta(days=setup_buffer_days),
                ).with_for_update()
            )
            if conflicts.scalars().first():
                raise BookingConflictError(
                    f"This resource is already booked or within the {setup_buffer_days}-day setup buffer"
                )

            booking = Booking(
                resource_id=resource_id,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                os_choice=os_choice,
                software_tags=software_tags or None,
                note=note or None,
            )
            session.add(booking)
        await session.refresh(booking)

    from not_dot_net.backend.audit import log_audit
    await log_audit(
        "booking", "create",
        actor_id=user_id,
        target_type="resource", target_id=resource_id,
        detail=f"{start_date} → {end_date}",
    )
    return booking


async def cancel_booking(booking_id: uuid.UUID, user_id: uuid.UUID | None = None,
                         is_admin: bool = False, actor=None) -> None:
    async with session_scope() as session:
        booking = await session.get(Booking, booking_id)
        if booking is None:
            raise ValueError("Booking not found")

        if actor is not None:
            is_owner = booking.user_id == actor.id
            is_manager = await has_permissions(actor, MANAGE_BOOKINGS)
            if not is_owner and not is_manager:
                raise PermissionError("Can only cancel your own bookings")
            user_id = actor.id
        elif not is_admin and booking.user_id != user_id:
            raise PermissionError("Can only cancel your own bookings")

        resource_id = booking.resource_id
        await session.delete(booking)
        await session.commit()

    from not_dot_net.backend.audit import log_audit
    await log_audit(
        "booking", "cancel",
        actor_id=user_id,
        target_type="resource", target_id=resource_id,
        detail=f"booking={booking_id}",
    )


async def get_resource_by_id(resource_id: uuid.UUID) -> Resource | None:
    async with session_scope() as session:
        return await session.get(Resource, resource_id)


# --- Booking reminders ---


async def _booking_reminder_subject() -> str:
    cfg = await org_config.get()
    app_name = (cfg.app_name or "not-dot-net").strip() or "not-dot-net"
    return f"[{app_name}] Your booking is ending soon"


def render_booking_reminder_body(
    *,
    user: User,
    booking: Booking,
    resource: Resource,
) -> str:
    display_name = user.full_name or user.email
    software = ", ".join(booking.software_tags or []) or "-"
    return (
        f"<p>Hello {escape(display_name)},</p>"
        "<p>Your booking is ending soon.</p>"
        "<table>"
        f"<tr><td><strong>Resource</strong></td><td>{escape(resource.name)}</td></tr>"
        f"<tr><td><strong>Start date</strong></td><td>{booking.start_date}</td></tr>"
        f"<tr><td><strong>End date</strong></td><td>{booking.end_date}</td></tr>"
        f"<tr><td><strong>OS</strong></td><td>{escape(booking.os_choice or '-')}</td></tr>"
        f"<tr><td><strong>Software</strong></td><td>{escape(software)}</td></tr>"
        "</table>"
        "<p>Please prepare to return or release the resource at the end of your booking.</p>"
    )


async def send_booking_end_reminders(today: date | None = None) -> int:
    """Queue reminder emails for bookings ending within the configured lead window.

    Returns the number of reminder emails queued. Each booking is marked
    immediately after enqueueing to avoid duplicate reminders on later scans.
    """
    today = today or date.today()
    lead_days = (await bookings_config.get()).reminder_lead_days
    if lead_days is None:
        return 0
    latest_end = today + timedelta(days=lead_days)
    subject = await _booking_reminder_subject()
    now = datetime.now(timezone.utc)
    queued = 0

    async with session_scope() as session:
        result = await session.execute(
            select(Booking, User, Resource)
            .join(User, Booking.user_id == User.id)
            .join(Resource, Booking.resource_id == Resource.id)
            .where(
                Booking.reminder_sent_at.is_(None),
                Booking.end_date >= today,
                Booking.end_date <= latest_end,
                User.is_active.is_(True),
                User.email.is_not(None),
                User.email != "",
            )
            .order_by(Booking.end_date, Resource.name)
        )
        rows = list(result.all())

        for booking, user, resource in rows:
            await send_mail(
                user.email,
                subject,
                render_booking_reminder_body(user=user, booking=booking, resource=resource),
            )
            booking.reminder_sent_at = now
            await session.commit()
            queued += 1

    return queued


async def run_booking_reminder_job() -> None:
    """APScheduler entrypoint for booking reminder emails."""
    try:
        queued = await send_booking_end_reminders()
        if queued:
            logger.info("Queued %d booking reminder email(s)", queued)
    except Exception:
        logger.exception("Booking reminder job failed")
