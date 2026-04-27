import pytest
import uuid
from datetime import date
from contextlib import asynccontextmanager

from not_dot_net.backend.db import User, get_async_session
from not_dot_net.backend.tenure_service import (
    UserTenure,
    add_tenure,
    close_tenure,
    list_tenures,
    current_tenure,
)


async def _create_user(email="test@lpp.fr") -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(id=uuid.uuid4(), email=email, hashed_password="x", role="staff")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_add_tenure():
    user = await _create_user()
    tenure = await add_tenure(
        user_id=user.id,
        status="Intern",
        employer="CNRS",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 8, 31),
    )
    assert tenure.status == "Intern"
    assert tenure.employer == "CNRS"
    assert tenure.start_date == date(2026, 3, 1)
    assert tenure.end_date == date(2026, 8, 31)


async def test_add_open_tenure():
    user = await _create_user()
    tenure = await add_tenure(
        user_id=user.id,
        status="PhD",
        employer="Sorbonne Université",
        start_date=date(2026, 9, 1),
    )
    assert tenure.end_date is None


async def test_current_tenure_returns_latest_open():
    user = await _create_user()
    await add_tenure(
        user_id=user.id, status="Intern", employer="CNRS",
        start_date=date(2025, 3, 1), end_date=date(2025, 8, 31),
    )
    await add_tenure(
        user_id=user.id, status="PhD", employer="Polytechnique",
        start_date=date(2025, 9, 1),
    )
    cur = await current_tenure(user.id)
    assert cur is not None
    assert cur.status == "PhD"
    assert cur.employer == "Polytechnique"


async def test_current_tenure_none_when_all_closed():
    user = await _create_user()
    await add_tenure(
        user_id=user.id, status="Intern", employer="CNRS",
        start_date=date(2025, 1, 1), end_date=date(2025, 6, 30),
    )
    assert await current_tenure(user.id) is None


async def test_close_tenure():
    user = await _create_user()
    tenure = await add_tenure(
        user_id=user.id, status="PhD", employer="CNRS",
        start_date=date(2025, 9, 1),
    )
    closed = await close_tenure(tenure.id, end_date=date(2026, 8, 31))
    assert closed.end_date == date(2026, 8, 31)


async def test_list_tenures_ordered():
    user = await _create_user()
    await add_tenure(
        user_id=user.id, status="Intern", employer="CNRS",
        start_date=date(2024, 3, 1), end_date=date(2024, 8, 31),
    )
    await add_tenure(
        user_id=user.id, status="PhD", employer="Polytechnique",
        start_date=date(2024, 9, 1),
    )
    tenures = await list_tenures(user.id)
    assert len(tenures) == 2
    assert tenures[0].start_date < tenures[1].start_date
