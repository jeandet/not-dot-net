import uuid

from not_dot_net.backend.db import User, session_scope


SUPPORTED_USER_LOCALES = {"en", "fr"}


def normalize_user_locale(locale: str | None) -> str | None:
    if locale in SUPPORTED_USER_LOCALES:
        return locale
    return None


async def save_user_locale(user_id: uuid.UUID, locale: str) -> bool:
    locale = normalize_user_locale(locale)
    if locale is None:
        return False

    async with session_scope() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        user.preferred_locale = locale
        await session.commit()
    return True
