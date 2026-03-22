"""Booking service — resource CRUD and reservation management."""

import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta

from sqlalchemy import and_, select

from not_dot_net.backend.booking_models import Booking, Resource
from not_dot_net.backend.db import get_async_session

MAX_BOOKING_DAYS = 183  # ~6 months


class BookingConflictError(Exception):
    pass


class BookingValidationError(Exception):
    pass


# --- Resources ---


async def list_resources(active_only: bool = True) -> list[Resource]:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        query = select(Resource).order_by(Resource.name)
        if active_only:
            query = query.where(Resource.active == True)  # noqa: E712
        result = await session.execute(query)
        return list(result.scalars().all())


async def create_resource(name: str, resource_type: str, description: str = "", location: str = "") -> Resource:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        resource = Resource(
            name=name,
            resource_type=resource_type,
            description=description or None,
            location=location or None,
        )
        session.add(resource)
        await session.commit()
        await session.refresh(resource)

    from not_dot_net.backend.audit import log_audit
    await log_audit(
        "resource", "create",
        target_type="resource", target_id=resource.id,
        detail=f"name={name} type={resource_type}",
    )
    return resource


async def update_resource(resource_id: uuid.UUID, **kwargs) -> Resource:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        resource = await session.get(Resource, resource_id)
        if resource is None:
            raise ValueError(f"Resource {resource_id} not found")
        for key, value in kwargs.items():
            if hasattr(resource, key):
                setattr(resource, key, value)
        await session.commit()
        await session.refresh(resource)
        return resource


async def delete_resource(resource_id: uuid.UUID) -> None:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        resource = await session.get(Resource, resource_id)
        if resource is None:
            raise ValueError(f"Resource {resource_id} not found")
        await session.delete(resource)
        await session.commit()


# --- Bookings ---


async def list_bookings_for_resource(
    resource_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None,
) -> list[Booking]:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
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
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        result = await session.execute(
            select(Booking)
            .where(Booking.user_id == user_id, Booking.end_date >= date.today())
            .order_by(Booking.start_date)
        )
        return list(result.scalars().all())


async def create_booking(
    resource_id: uuid.UUID, user_id: uuid.UUID,
    start_date: date, end_date: date, note: str = "",
) -> Booking:
    if start_date >= end_date:
        raise BookingValidationError("End date must be after start date")
    if start_date < date.today():
        raise BookingValidationError("Cannot book in the past")
    if (end_date - start_date).days > MAX_BOOKING_DAYS:
        raise BookingValidationError(f"Booking cannot exceed {MAX_BOOKING_DAYS} days")

    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        # Check for overlapping bookings
        conflicts = await session.execute(
            select(Booking).where(
                Booking.resource_id == resource_id,
                Booking.start_date < end_date,
                Booking.end_date > start_date,
            )
        )
        if conflicts.scalars().first():
            raise BookingConflictError("This resource is already booked for the selected period")

        booking = Booking(
            resource_id=resource_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            note=note or None,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

    from not_dot_net.backend.audit import log_audit
    await log_audit(
        "booking", "create",
        actor_id=user_id,
        target_type="resource", target_id=resource_id,
        detail=f"{start_date} → {end_date}",
    )
    return booking


async def cancel_booking(booking_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False) -> None:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking is None:
            raise ValueError("Booking not found")
        if not is_admin and booking.user_id != user_id:
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
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        return await session.get(Resource, resource_id)
