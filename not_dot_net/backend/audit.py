"""Audit logging — structured event recording to DB + Python logging."""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import JSON, String, Text, func, select
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from not_dot_net.backend.db import Base, get_async_session

logger = logging.getLogger("not_dot_net.audit")


class AuditEvent(MappedAsDataclass, Base, kw_only=True):
    __tablename__ = "audit_event"

    category: Mapped[str] = mapped_column(String(50))   # auth, user, workflow, booking, resource
    action: Mapped[str] = mapped_column(String(100))     # login, create, update, delete, approve, reject, book, cancel
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)  # user, request, resource, booking
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), default=None)


async def log_audit(
    category: str,
    action: str,
    actor_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Record an audit event to the database and Python logger."""
    actor_str = str(actor_id) if actor_id else None
    target_str = str(target_id) if target_id else None

    log_msg = f"[{category}] {action}"
    if actor_email:
        log_msg += f" by={actor_email}"
    if target_type and target_str:
        log_msg += f" {target_type}={target_str}"
    if detail:
        log_msg += f" — {detail}"
    logger.info(log_msg)

    try:
        get_session = asynccontextmanager(get_async_session)
        async with get_session() as session:
            event = AuditEvent(
                category=category,
                action=action,
                actor_id=actor_str,
                actor_email=actor_email,
                target_type=target_type,
                target_id=target_str,
                detail=detail,
                metadata_json=metadata,
            )
            session.add(event)
            await session.commit()
    except Exception:
        logger.exception("Failed to write audit event to DB")


async def list_audit_events(
    category: str | None = None,
    action: str | None = None,
    actor_email: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        query = select(AuditEvent).order_by(AuditEvent.created_at.desc())
        if category:
            query = query.where(AuditEvent.category == category)
        if action:
            query = query.where(AuditEvent.action == action)
        if actor_email:
            query = query.where(AuditEvent.actor_email.ilike(f"%{actor_email}%"))
        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        events = list(result.scalars().all())

        # Resolve UUIDs to human-readable names
        await _resolve_names(session, events)
        return events


async def _resolve_names(session, events: list[AuditEvent]) -> None:
    """Enrich events with human-readable actor_email and target display names."""
    from not_dot_net.backend.booking_models import Resource
    from not_dot_net.backend.db import User

    actor_ids = {
        ev.actor_id for ev in events if ev.actor_id and not ev.actor_email
    }
    target_user_ids = {
        ev.target_id for ev in events if ev.target_type == "user" and ev.target_id
    }
    target_resource_ids = {
        ev.target_id for ev in events if ev.target_type == "resource" and ev.target_id
    }

    user_ids_to_resolve = actor_ids | target_user_ids
    user_names: dict[str, str] = {}
    if user_ids_to_resolve:
        rows = await session.execute(
            select(User.id, User.email, User.full_name).where(
                User.id.in_([uuid.UUID(uid) for uid in user_ids_to_resolve])
            )
        )
        for uid, email, full_name in rows:
            user_names[str(uid)] = full_name or email

    resource_names: dict[str, str] = {}
    if target_resource_ids:
        rows = await session.execute(
            select(Resource.id, Resource.name).where(
                Resource.id.in_([uuid.UUID(rid) for rid in target_resource_ids])
            )
        )
        for rid, name in rows:
            resource_names[str(rid)] = name

    for ev in events:
        if ev.actor_id and not ev.actor_email and ev.actor_id in user_names:
            ev.actor_email = user_names[ev.actor_id]
        if ev.target_id:
            if ev.target_type == "user" and ev.target_id in user_names:
                ev.target_id = user_names[ev.target_id]
            elif ev.target_type == "resource" and ev.target_id in resource_names:
                ev.target_id = resource_names[ev.target_id]
