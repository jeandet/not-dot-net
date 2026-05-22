import pytest

from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.user_preferences import normalize_user_locale, save_user_locale


def test_normalize_user_locale_accepts_supported_locales():
    assert normalize_user_locale("en") == "en"
    assert normalize_user_locale("fr") == "fr"


def test_normalize_user_locale_rejects_unsupported_locale():
    assert normalize_user_locale("de") is None
    assert normalize_user_locale("") is None
    assert normalize_user_locale(None) is None


@pytest.mark.asyncio
async def test_save_user_locale_persists_supported_locale():
    async with session_scope() as session:
        user = User(email="locale@test.dev", hashed_password="x")
        session.add(user)
        await session.commit()
        user_id = user.id

    assert await save_user_locale(user_id, "fr") is True

    async with session_scope() as session:
        user = await session.get(User, user_id)
        assert user.preferred_locale == "fr"


@pytest.mark.asyncio
async def test_save_user_locale_rejects_unsupported_locale():
    async with session_scope() as session:
        user = User(email="bad-locale@test.dev", hashed_password="x")
        session.add(user)
        await session.commit()
        user_id = user.id

    assert await save_user_locale(user_id, "de") is False

    async with session_scope() as session:
        user = await session.get(User, user_id)
        assert user.preferred_locale is None
