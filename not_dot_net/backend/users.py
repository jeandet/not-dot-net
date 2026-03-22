import logging
import uuid
from contextlib import asynccontextmanager

logger = logging.getLogger("not_dot_net.users")

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
from not_dot_net.backend.roles import Role
from not_dot_net.config import get_settings


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    @property
    def reset_password_token_secret(self):
        return get_settings().jwt_secret

    @property
    def verification_token_secret(self):
        return get_settings().jwt_secret

    async def on_after_register(self, user: User, request: Request | None = None):
        logger.info("User %s registered", user.id)

    async def on_after_update(self, user: User, update_dict: dict, request: Request | None = None):
        if "role" in update_dict:
            user.is_superuser = (user.role == Role.ADMIN)
            await self.user_db.update(user, {"is_superuser": user.role == Role.ADMIN})


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


async def ensure_default_admin() -> None:
    """Create default admin user if it doesn't exist yet."""
    from not_dot_net.backend.db import get_async_session, get_user_db
    from not_dot_net.backend.schemas import UserCreate
    from fastapi_users.exceptions import UserAlreadyExists

    settings = get_settings()

    get_session_ctx = asynccontextmanager(get_async_session)
    get_user_db_ctx = asynccontextmanager(get_user_db)
    get_user_manager_ctx = asynccontextmanager(get_user_manager)

    async with get_session_ctx() as session:
        async with get_user_db_ctx(session) as user_db:
            async with get_user_manager_ctx(user_db) as user_manager:
                try:
                    user = await user_manager.create(
                        UserCreate(
                            email=settings.admin_email,
                            password=settings.admin_password,
                            is_active=True,
                            is_superuser=True,
                        )
                    )
                    user.role = Role.ADMIN
                    session.add(user)
                    await session.commit()
                    logger.info("Default admin '%s' created", settings.admin_email)
                except UserAlreadyExists:
                    pass


async def seed_fake_users() -> None:
    """Seed ~100 fake users + ~20 workflows for development."""
    from not_dot_net.backend.db import get_async_session, get_user_db
    from not_dot_net.backend.schemas import UserCreate
    from not_dot_net.backend.seed_data import FAKE_USERS
    from fastapi_users.exceptions import UserAlreadyExists

    get_session_ctx = asynccontextmanager(get_async_session)
    get_user_db_ctx = asynccontextmanager(get_user_db)
    get_user_manager_ctx = asynccontextmanager(get_user_manager)

    created_users = []
    async with get_session_ctx() as session:
        async with get_user_db_ctx(session) as user_db:
            async with get_user_manager_ctx(user_db) as user_manager:
                count = 0
                for fake in FAKE_USERS:
                    try:
                        user = await user_manager.create(
                            UserCreate(
                                email=fake["email"],
                                password="dev",
                                is_active=True,
                                is_superuser=False,
                            )
                        )
                        for field in ("full_name", "phone", "office", "team", "title", "employment_status"):
                            setattr(user, field, fake.get(field))
                        if fake.get("start_date"):
                            from datetime import date as _date
                            user.start_date = _date.fromisoformat(fake["start_date"])
                        if fake.get("end_date"):
                            from datetime import date as _date
                            user.end_date = _date.fromisoformat(fake["end_date"])
                        user.role = Role(fake["role"])
                        session.add(user)
                        created_users.append(user)
                        count += 1
                    except UserAlreadyExists:
                        pass
                await session.commit()
                if count:
                    logger.info("Seeded %d fake users", count)

    if created_users:
        await _seed_fake_workflows(created_users)
    await _seed_resources_and_bookings(created_users)


async def _seed_fake_workflows(users: list) -> None:
    """Seed ~20 workflow requests in various states."""
    import random as _random
    from not_dot_net.backend.seed_data import WORKFLOW_SEEDS
    from not_dot_net.backend.workflow_service import create_request, submit_step

    rng = _random.Random(42)

    staff = [u for u in users if u.role in (Role.STAFF, Role.DIRECTOR, Role.ADMIN)]
    directors = [u for u in users if u.role == Role.DIRECTOR]
    admins = [u for u in users if u.role == Role.ADMIN]

    if not staff:
        return

    count = 0
    for seed in WORKFLOW_SEEDS:
        creator = rng.choice(staff)
        try:
            req = await create_request(
                workflow_type=seed["type"],
                created_by=creator.id,
                data=seed["data"],
            )

            # Advance through steps based on seed config
            if seed["step"] == "request" and seed["action"] is None:
                pass  # stays at first step
            elif seed["action"] == "submit":
                await submit_step(req.id, creator.id, "submit", data={})
            elif seed["action"] == "approve":
                await submit_step(req.id, creator.id, "submit", data={})
                approver = rng.choice(directors) if directors else creator
                # For onboarding, submit newcomer_info step too if needed
                if seed["type"] == "onboarding" and seed["step"] in ("admin_validation", "done"):
                    await submit_step(req.id, None, "submit", data=seed["data"])
                await submit_step(
                    req.id, approver.id, "approve",
                    comment=seed.get("comment"),
                )
            elif seed["action"] == "reject":
                await submit_step(req.id, creator.id, "submit", data={})
                approver = rng.choice(directors) if directors else creator
                if seed["type"] == "onboarding" and seed["step"] == "rejected":
                    await submit_step(req.id, None, "submit", data=seed["data"])
                await submit_step(
                    req.id, approver.id, "reject",
                    comment=seed.get("comment"),
                )

            count += 1
        except Exception as e:
            logger.warning("Seed workflow failed: %s", e)

    if count:
        logger.info("Seeded %d workflow requests", count)


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
                    from not_dot_net.backend.audit import log_audit
                    await log_audit("auth", "login_failed", detail=f"email={email}")
                    return None
                from not_dot_net.backend.audit import log_audit
                await log_audit(
                    "auth", "login",
                    actor_id=user.id, actor_email=user.email,
                )
                strategy = cookie_backend.get_strategy()
                return await strategy.write_token(user)


async def _seed_resources_and_bookings(users: list) -> None:
    """Seed resources and a few sample bookings."""
    import random as _random
    from datetime import date, timedelta
    from not_dot_net.backend.seed_data import SEED_RESOURCES
    from not_dot_net.backend.booking_service import (
        create_resource,
        create_booking,
        list_resources,
    )

    existing = await list_resources(active_only=False)
    if existing:
        return  # already seeded

    rng = _random.Random(42)
    resources = []
    for seed in SEED_RESOURCES:
        res = await create_resource(
            name=seed["name"],
            resource_type=seed["type"],
            description=seed.get("description", ""),
            location=seed.get("location", ""),
            specs=seed.get("specs"),
        )
        resources.append(res)

    if not users:
        logger.info("Seeded %d resources", len(resources))
        return

    # Create some bookings
    today = date.today()
    count = 0
    for res in resources[:5]:
        booker = rng.choice(users)
        start = today + timedelta(days=rng.randint(1, 30))
        end = start + timedelta(days=rng.randint(1, 14))
        try:
            await create_booking(res.id, booker.id, start, end, note="Dev seed booking")
            count += 1
        except Exception:
            pass

    logger.info("Seeded %d resources, %d bookings", len(resources), count)
