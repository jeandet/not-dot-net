import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from not_dot_net.backend.db import User, get_user_db
from not_dot_net.config import get_settings


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    @property
    def reset_password_token_secret(self):
        return get_settings().jwt_secret

    @property
    def verification_token_secret(self):
        return get_settings().jwt_secret

    async def on_after_register(self, user: User, request: Request | None = None):
        print(f"User {user.id} has registered.")


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
cookie_transport = CookieTransport(
    cookie_name="fastapiusersauth",
    cookie_max_age=3600,
    cookie_httponly=False,
)


def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    return JWTStrategy(secret=get_settings().jwt_secret, lifetime_seconds=3600)


jwt_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

cookie_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager, [jwt_backend, cookie_backend]
)

current_active_user = fastapi_users.current_user(active=True)
current_active_user_optional = fastapi_users.current_user(active=True, optional=True)


async def authenticate_and_get_token(email: str, password: str) -> str | None:
    """Authenticate a user and return a cookie token, or None on failure.

    Intended for use in NiceGUI page callbacks where FastAPI DI is not available.
    """
    from not_dot_net.backend.db import get_async_session, get_user_db
    from fastapi.security import OAuth2PasswordRequestForm

    get_session_ctx = asynccontextmanager(get_async_session)
    get_user_db_ctx = asynccontextmanager(get_user_db)
    get_user_manager_ctx = asynccontextmanager(get_user_manager)

    async with get_session_ctx() as session:
        async with get_user_db_ctx(session) as user_db:
            async with get_user_manager_ctx(user_db) as user_manager:
                credentials = OAuth2PasswordRequestForm(
                    username=email, password=password, scope="", grant_type="password"
                )
                user = await user_manager.authenticate(credentials)
                if user is None or not user.is_active:
                    return None
                strategy = cookie_backend.get_strategy()
                return await strategy.write_token(user)
