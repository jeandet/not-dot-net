"""User tenure tracking — employment periods with status and employer."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String, func, select
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from not_dot_net.backend.db import Base, session_scope


class UserTenure(MappedAsDataclass, Base, kw_only=True):
    __tablename__ = "user_tenure"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(100))
    employer: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default_factory=uuid.uuid4)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), default=None)


async def add_tenure(
    user_id: uuid.UUID,
    status: str,
    employer: str,
    start_date: date,
    end_date: date | None = None,
    notes: str | None = None,
) -> UserTenure:
    async with session_scope() as session:
        tenure = UserTenure(
            user_id=user_id,
            status=status,
            employer=employer,
            start_date=start_date,
            end_date=end_date,
            notes=notes,
        )
        session.add(tenure)
        await session.commit()
        await session.refresh(tenure)
        return tenure


async def close_tenure(tenure_id: uuid.UUID, end_date: date) -> UserTenure:
    async with session_scope() as session:
        tenure = await session.get(UserTenure, tenure_id)
        if tenure is None:
            raise ValueError(f"Tenure {tenure_id} not found")
        tenure.end_date = end_date
        await session.commit()
        await session.refresh(tenure)
        return tenure


async def list_tenures(user_id: uuid.UUID) -> list[UserTenure]:
    async with session_scope() as session:
        result = await session.execute(
            select(UserTenure)
            .where(UserTenure.user_id == user_id)
            .order_by(UserTenure.start_date.asc())
        )
        return list(result.scalars().all())


async def current_tenure(user_id: uuid.UUID) -> UserTenure | None:
    async with session_scope() as session:
        result = await session.execute(
            select(UserTenure)
            .where(UserTenure.user_id == user_id, UserTenure.end_date == None)  # noqa: E711
            .order_by(UserTenure.start_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
