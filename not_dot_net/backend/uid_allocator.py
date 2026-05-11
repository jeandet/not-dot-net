"""Centralized Unix UID allocator. PK enforces no-reuse."""
from __future__ import annotations
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, MappedAsDataclass

from not_dot_net.backend.db import Base, session_scope


class UidRangeExhausted(Exception):
    """No free UID left in the configured range."""


class UidAllocation(MappedAsDataclass, Base, kw_only=True):
    __tablename__ = "uid_allocation"

    uid: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # 'allocated' | 'seeded_from_ad'
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, default=None,
    )
    sam_account: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=None,
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)


@dataclass(frozen=True)
class UidAllocationView:
    uid: int
    source: str
    user_id: uuid.UUID | None
    sam_account: str | None
    acquired_at: datetime
    note: str | None


async def allocate_uid(user_id: uuid.UUID, sam_account: str) -> int:
    """Allocate the smallest free UID in the configured [uid_min, uid_max] range.

    Inserts a row marking the UID consumed; raises UidRangeExhausted if no free slot.
    Audit-logs the allocation with category='ad' action='allocate_uid'.
    """
    from not_dot_net.backend.ad_account_config import ad_account_config
    from not_dot_net.backend.audit import log_audit

    cfg = await ad_account_config.get()
    lo, hi = cfg.uid_min, cfg.uid_max

    async with session_scope() as session:
        rows = (await session.execute(
            select(UidAllocation.uid).where(
                UidAllocation.uid >= lo, UidAllocation.uid <= hi,
            ).order_by(UidAllocation.uid.asc())
        )).scalars().all()

        used = set(rows)
        chosen: int | None = None
        for n in range(lo, hi + 1):
            if n not in used:
                chosen = n
                break
        if chosen is None:
            raise UidRangeExhausted(f"No free UID in [{lo}, {hi}]")

        session.add(UidAllocation(
            uid=chosen, source="allocated",
            user_id=user_id, sam_account=sam_account,
        ))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise UidRangeExhausted(
                f"UID {chosen} was taken concurrently — retry with a fresh session"
            )

    await log_audit(
        category="ad", action="allocate_uid",
        actor_id=None, target_id=str(user_id),
        detail=f"uid={chosen} sam={sam_account}",
    )
    return chosen


@dataclass(frozen=True)
class SeedResult:
    seeded: int
    skipped: int


def _search_ad_uids(ldap_cfg, bind_username: str, bind_password: str):
    """Bind and paged-search AD for entries with uidNumber. Returns list of ldap3 entries.

    Wrapped in its own function so tests can monkeypatch it.
    """
    from ldap3 import SUBTREE
    from not_dot_net.backend.auth.ldap import _ldap_bind, get_ldap_connect

    conn = _ldap_bind(bind_username, bind_password, ldap_cfg, get_ldap_connect())
    try:
        ok = conn.search(
            search_base=ldap_cfg.base_dn,
            search_filter="(&(objectClass=user)(uidNumber=*))",
            search_scope=SUBTREE,
            attributes=["uidNumber", "sAMAccountName"],
            paged_size=500,
        )
        if not ok:
            return []
        return list(conn.entries)
    finally:
        conn.unbind()


async def seed_from_ad(bind_username: str, bind_password: str) -> SeedResult:
    """Lock all existing AD UIDs into the allocation table. Idempotent."""
    from not_dot_net.backend.ad_account_config import ad_account_config
    from not_dot_net.backend.auth.ldap import ldap_config
    from not_dot_net.backend.audit import log_audit

    ldap_cfg = await ldap_config.get()
    _ = await ad_account_config.get()  # ensure section materialized

    entries = _search_ad_uids(ldap_cfg, bind_username, bind_password)
    seeded = 0
    skipped = 0
    async with session_scope() as session:
        existing = set(
            (await session.execute(select(UidAllocation.uid))).scalars().all()
        )
        for entry in entries:
            uid_val = entry.uidNumber.value
            if uid_val is None:
                continue
            uid_int = int(uid_val)
            if uid_int in existing:
                skipped += 1
                continue
            sam = entry.sAMAccountName.value if entry.sAMAccountName.value else None
            session.add(UidAllocation(
                uid=uid_int,
                source="seeded_from_ad",
                user_id=None,
                sam_account=sam,
            ))
            existing.add(uid_int)
            seeded += 1
        await session.commit()

    await log_audit(
        category="ad", action="seed_uids",
        actor_id=None, target_id=None,
        detail=f"seeded={seeded} skipped={skipped}",
    )
    return SeedResult(seeded=seeded, skipped=skipped)


async def list_allocations(*, limit: int = 200) -> list[UidAllocationView]:
    """List all UID allocations, most recent first."""
    async with session_scope() as session:
        rows = (await session.execute(
            select(UidAllocation).order_by(UidAllocation.acquired_at.desc()).limit(limit)
        )).scalars().all()
    return [
        UidAllocationView(
            uid=r.uid, source=r.source, user_id=r.user_id,
            sam_account=r.sam_account, acquired_at=r.acquired_at, note=r.note,
        )
        for r in rows
    ]
