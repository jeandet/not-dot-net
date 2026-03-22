"""Runtime-editable app settings stored in DB, with config file defaults."""

from contextlib import asynccontextmanager

from sqlalchemy import JSON, String, select
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from not_dot_net.backend.db import Base, get_async_session
from not_dot_net.config import get_settings


class AppSetting(MappedAsDataclass, Base, kw_only=True):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list] = mapped_column(JSON)


async def _get(key: str):
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        row = await session.get(AppSetting, key)
        return row.value if row else None


async def _set(key: str, value):
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        row = await session.get(AppSetting, key)
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value))
        await session.commit()


async def get_os_choices() -> list[str]:
    val = await _get("os_choices")
    return val if val is not None else get_settings().os_choices


async def set_os_choices(choices: list[str]) -> None:
    await _set("os_choices", choices)


async def get_software_tags() -> dict[str, list[str]]:
    val = await _get("software_tags")
    return val if val is not None else get_settings().software_tags


async def set_software_tags(tags: dict[str, list[str]]) -> None:
    await _set("software_tags", tags)
