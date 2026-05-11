# FastAPI/Pydantic Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor not-dot-net to follow idiomatic FastAPI, Pydantic, and fastapi-users patterns.

**Architecture:** Replace the custom plugin-registry and god-object patterns with standard FastAPI dependency injection, explicit APIRouter usage, and module-level dependency providers. Fix bugs (async call in CLI, missing DB column). Clean up configuration to use proper pydantic-settings nesting.

**Tech Stack:** NiceGUI 3.9, FastAPI-Users 15.0.4, SQLAlchemy 2.x async, Pydantic Settings

---

## File Structure

After refactoring:

```
not_dot_net/
  app.py           # App class with lifespan, ui.run() — simplified
  cli.py           # cyclopts CLI — fix async call
  config.py        # Settings (BaseSettings), nested BaseModel classes
  backend/
    __init__.py    # empty
    db.py          # module-level engine/session, get_async_session, get_user_db, User model
    schemas.py     # UserRead, UserCreate, UserUpdate (unchanged)
    users.py       # UserManager, auth backends, current_active_user deps
    auth/
      local.py     # APIRouter with POST endpoints
      ldap.py      # APIRouter with POST endpoints
  frontend/
    __init__.py    # empty
    login.py       # @ui.page("/login") — uses httpx to POST /auth/cookie/login
    user_page.py   # @ui.page("/user/profile")
```

**Deleted files:**
- `backend/app.py` — dissolved into `app.py` and `backend/users.py`
- `backend/users/` directory (moved `users.py` up to `backend/users.py`)
- `backend/users/auth/register.py` — plugin registry removed
- `backend/users/auth/__init__.py` — plugin registry removed
- `backend/users/__init__.py` — re-export removed
- `frontend/register.py` — plugin registry removed
- `backend/users/auth/ldap/__init__.py` — flattened

---

### Task 1: Fix config.py — nested BaseModel, restore source chain

**Files:**
- Modify: `not_dot_net/config.py`

- [ ] **Step 1: Rewrite config.py**

Change nested settings classes from `BaseSettings` to `BaseModel`. Restore env/init sources alongside YAML. Remove `app.state` storage — use a module-level cached singleton instead.

```python
from functools import lru_cache
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
    PydanticBaseSettingsSource,
)


class LDAPSettings(BaseModel):
    url: str = "ldap://localhost"
    base_dn: str = "dc=example,dc=com"
    port: int = 389


class AuthSettings(BaseModel):
    ldap: LDAPSettings = LDAPSettings()


class UsersSettings(BaseModel):
    auth: AuthSettings = AuthSettings()


class BackendSettings(BaseModel):
    users: UsersSettings = UsersSettings()
    database_url: str = "sqlite+aiosqlite:///./test.db"


class Settings(BaseSettings):
    app_name: str = "LPP Intranet"
    admin_email: str = ""
    backend: BackendSettings = BackendSettings()

    model_config = SettingsConfigDict(yaml_file="config.yaml")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )


_settings: Settings | None = None


def init_settings(config_file: str | None = None) -> Settings:
    global _settings
    _settings = Settings(_yaml_file=config_file)
    return _settings


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings not initialized — call init_settings() first")
    return _settings
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from not_dot_net.config import Settings; print(Settings())"`

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/config.py
git commit -m "refactor: config uses BaseModel for nested settings, restore env source chain"
```

---

### Task 2: Rewrite db.py — module-level deps, fix User.auth_method column

**Files:**
- Modify: `not_dot_net/backend/db.py`

- [ ] **Step 1: Rewrite db.py**

Module-level engine/session maker initialized by an `init_db()` function. `get_async_session` and `get_user_db` as module-level async generators. Fix `auth_method` as a proper mapped column.

```python
from collections.abc import AsyncGenerator
from enum import Enum as PyEnum

from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AuthMethod(str, PyEnum):
    LOCAL = "local"
    LDAP = "ldap"


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    auth_method: Mapped[AuthMethod] = mapped_column(
        SAEnum(AuthMethod), default=AuthMethod.LOCAL
    )


_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    global _async_session_maker
    engine = create_async_engine(database_url)
    _async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables() -> None:
    if _async_session_maker is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    engine = _async_session_maker.kw["bind"]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    if _async_session_maker is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    async with _async_session_maker() as session:
        yield session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from not_dot_net.backend.db import User, init_db, get_async_session; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/backend/db.py
git commit -m "refactor: db.py uses module-level deps, fix auth_method as mapped_column"
```

---

### Task 3: Rewrite users.py — flatten to backend/users.py, module-level deps

**Files:**
- Create: `not_dot_net/backend/users.py`
- Delete: `not_dot_net/backend/users/users.py`
- Delete: `not_dot_net/backend/users/__init__.py`
- Delete: `not_dot_net/backend/users/auth/register.py`
- Delete: `not_dot_net/backend/users/auth/__init__.py`
- Delete: `not_dot_net/backend/users/auth/ldap/__init__.py`
- Modify: `not_dot_net/backend/__init__.py`

- [ ] **Step 1: Create backend/users.py**

Module-level user manager, auth backends, and dependency providers.

```python
import uuid

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

SECRET = "SECRET"


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

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
)


def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


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
```

- [ ] **Step 2: Empty backend/__init__.py**

Replace contents with empty file (or just a pass).

- [ ] **Step 3: Delete old users directory structure**

```bash
rm not_dot_net/backend/users/users.py
rm not_dot_net/backend/users/__init__.py
rm not_dot_net/backend/users/auth/register.py
rm not_dot_net/backend/users/auth/__init__.py
rm not_dot_net/backend/users/auth/ldap/__init__.py
```

- [ ] **Step 4: Verify import works**

Run: `uv run python -c "from not_dot_net.backend.users import fastapi_users, current_active_user; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add -A not_dot_net/backend/
git commit -m "refactor: flatten users.py to backend/users.py, module-level auth deps"
```

---

### Task 4: Rewrite auth endpoints as APIRouter — local.py and ldap.py

**Files:**
- Modify: `not_dot_net/backend/auth/local.py` (move from `backend/users/auth/local.py`)
- Modify: `not_dot_net/backend/auth/ldap.py` (move from `backend/users/auth/ldap/ldap.py`)
- Create: `not_dot_net/backend/auth/__init__.py`

- [ ] **Step 1: Create backend/auth/__init__.py**

```python
from fastapi import APIRouter

from .local import router as local_router
from .ldap import router as ldap_router

router = APIRouter()
router.include_router(local_router)
router.include_router(ldap_router)
```

- [ ] **Step 2: Rewrite backend/auth/local.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users.db import SQLAlchemyUserDatabase
from passlib.context import CryptContext
from pydantic import BaseModel

from not_dot_net.backend.db import get_user_db
from not_dot_net.backend.users import get_user_manager, get_jwt_strategy
from not_dot_net.backend.schemas import UserCreate

router = APIRouter(tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


@router.post("/auth/local", response_model=TokenResponse)
async def local_login(
    credentials: AuthRequest,
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    user = await user_db.get_by_email(credentials.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    hashed = getattr(user, "hashed_password", None)
    if not hashed or not pwd_context.verify(credentials.password, hashed):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    strategy = get_jwt_strategy()
    token = strategy.write_token(user)
    return TokenResponse(access_token=token)


@router.post("/auth/register", response_model=TokenResponse)
async def local_register(
    credentials: AuthRequest,
    user_manager=Depends(get_user_manager),
):
    user_create = UserCreate(email=credentials.email, password=credentials.password)
    try:
        user = await user_manager.create(user_create)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    strategy = get_jwt_strategy()
    token = strategy.write_token(user)
    return TokenResponse(access_token=token)
```

- [ ] **Step 3: Rewrite backend/auth/ldap.py**

Uses settings for LDAP config instead of `os.environ`.

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users.db import SQLAlchemyUserDatabase
from ldap3 import Server, Connection, ALL
from ldap3.core.exceptions import LDAPBindError
from pydantic import BaseModel

from not_dot_net.backend.db import get_user_db
from not_dot_net.backend.users import get_jwt_strategy
from not_dot_net.config import get_settings

router = APIRouter(tags=["auth"])


class LDAPAuthRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


@router.post("/auth/ldap", response_model=TokenResponse)
async def ldap_login(
    credentials: LDAPAuthRequest,
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    ldap_cfg = get_settings().backend.users.auth.ldap
    server = Server(ldap_cfg.url, get_info=ALL)

    try:
        user_dn = f"uid={credentials.username},{ldap_cfg.base_dn}"
        conn = Connection(server, user=user_dn, password=credentials.password, auto_bind=True)
    except LDAPBindError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid LDAP credentials")

    try:
        conn.search(ldap_cfg.base_dn, f"(uid={credentials.username})", attributes=["mail"])
        if not conn.entries:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="LDAP user not found")
        email = getattr(conn.entries[0], "mail", None)
        email_value = email.value if email is not None else None
    finally:
        conn.unbind()

    if not email_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LDAP did not return email")

    user = await user_db.get_by_email(email_value)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No local user mapped to this LDAP account",
        )

    strategy = get_jwt_strategy()
    token = strategy.write_token(user)
    return TokenResponse(access_token=token)
```

- [ ] **Step 4: Delete old auth files**

```bash
rm -r not_dot_net/backend/users/auth/
rmdir not_dot_net/backend/users/ 2>/dev/null || true
```

- [ ] **Step 5: Verify imports**

Run: `uv run python -c "from not_dot_net.backend.auth import router; print(router.routes)"`

- [ ] **Step 6: Commit**

```bash
git add -A not_dot_net/backend/auth/ not_dot_net/backend/users/
git commit -m "refactor: auth endpoints as APIRouter, LDAP uses Settings"
```

---

### Task 5: Rewrite app.py — lifespan, simplified wiring, remove NotDotNetApp

**Files:**
- Modify: `not_dot_net/app.py`
- Delete: `not_dot_net/backend/app.py`

- [ ] **Step 1: Rewrite app.py**

```python
from typing import Optional
from contextlib import asynccontextmanager

from nicegui import app, ui

from not_dot_net.config import init_settings, get_settings
from not_dot_net.backend.db import init_db, create_db_and_tables
from not_dot_net.backend.users import fastapi_users, jwt_backend, cookie_backend
from not_dot_net.backend.schemas import UserRead, UserUpdate
from not_dot_net.backend.auth import router as auth_router
from not_dot_net.frontend.login import setup as setup_login
from not_dot_net.frontend.user_page import setup as setup_user_page


def create_app(config_file: str | None = None):
    settings = init_settings(config_file)
    init_db(settings.backend.database_url)

    app.on_startup(create_db_and_tables)

    app.include_router(
        fastapi_users.get_auth_router(jwt_backend),
        prefix="/auth/jwt",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_auth_router(cookie_backend),
        prefix="/auth/cookie",
        tags=["auth"],
    )
    app.include_router(
        fastapi_users.get_users_router(UserRead, UserUpdate),
        prefix="/users",
        tags=["users"],
    )
    app.include_router(auth_router)

    setup_login()
    setup_user_page()


@ui.page("/")
def main_page() -> None:
    with ui.header().classes(replace="row items-center") as header:
        ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
            "flat color=white"
        )
        with ui.tabs() as tabs:
            ui.tab("A")
            ui.tab("B")
            ui.tab("C")

    with ui.footer(value=False) as footer:
        ui.label("Footer")

    with ui.left_drawer().classes("bg-blue-100") as left_drawer:
        ui.label("Side menu")

    with ui.page_sticky(position="bottom-right", x_offset=20, y_offset=20):
        ui.button(on_click=footer.toggle, icon="contact_support").props("fab")

    with ui.tab_panels(tabs, value="A").classes("w-full"):
        with ui.tab_panel("A"):
            ui.label("Content of A")
        with ui.tab_panel("B"):
            ui.label("Content of B")
        with ui.tab_panel("C"):
            ui.label("Content of C")


def main(
    host: str = "localhost",
    port: int = 8000,
    env_file: Optional[str] = None,
    reload=False,
) -> None:
    create_app(env_file)
    ui.run(
        storage_secret="test", host=host, port=port, reload=reload, title="NotDotNet"
    )


if __name__ in {"__main__", "__mp_main__"}:
    main("localhost", 8000, None)
```

- [ ] **Step 2: Delete backend/app.py**

```bash
rm not_dot_net/backend/app.py
```

- [ ] **Step 3: Commit**

```bash
git add -A not_dot_net/app.py not_dot_net/backend/app.py
git commit -m "refactor: simplify app.py, remove NotDotNetApp god-object, add lifespan"
```

---

### Task 6: Rewrite frontend — remove registry, fix login flow

**Files:**
- Modify: `not_dot_net/frontend/__init__.py`
- Modify: `not_dot_net/frontend/login.py`
- Modify: `not_dot_net/frontend/user_page.py`
- Delete: `not_dot_net/frontend/register.py`

- [ ] **Step 1: Empty frontend/__init__.py**

No more auto-discovery. Pages are wired explicitly in `app.py`.

- [ ] **Step 2: Rewrite frontend/login.py**

POST to the cookie auth endpoint instead of manually reconstructing the DI graph. No more JS cookie injection.

```python
from typing import Optional

from fastapi.responses import RedirectResponse
from nicegui import app, ui
import httpx


def setup():
    @ui.page("/login")
    def login(redirect_to: str = "/user/profile") -> Optional[RedirectResponse]:
        if app.storage.user.get("authenticated", False):
            return RedirectResponse(redirect_to)

        async def try_login() -> None:
            try:
                async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
                    response = await client.post(
                        "/auth/cookie/login",
                        data={"username": email.value, "password": password.value},
                    )
                if response.status_code == 200:
                    cookie_value = response.cookies.get("fastapiusersauth")
                    if cookie_value:
                        ui.run_javascript(
                            f'document.cookie = "fastapiusersauth={cookie_value}; path=/; SameSite=Lax";'
                            f'window.location.href = "{redirect_to}";'
                        )
                else:
                    ui.notify("Invalid email or password", color="negative")
            except Exception:
                ui.notify("Auth server error", color="negative")

        with ui.card().classes("absolute-center"):
            email = ui.input("Email").on("keydown.enter", try_login)
            password = ui.input(
                "Password", password=True, password_toggle_button=True
            ).on("keydown.enter", try_login)
            ui.button("Log in", on_click=try_login)
        return None
```

- [ ] **Step 3: Rewrite frontend/user_page.py**

Import deps directly from `backend.users` instead of receiving `ndtapp`.

```python
from typing import Optional

from fastapi import Depends
from fastapi.responses import RedirectResponse
from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.users import current_active_user_optional


def setup():
    @ui.page("/user/profile")
    def user_page(
        user: Optional[User] = Depends(current_active_user_optional),
    ) -> Optional[RedirectResponse]:
        if not user:
            ui.notify("Please log in to access your user profile", color="warning")
            return RedirectResponse("/login")
        with ui.card().classes("absolute-center"):
            ui.label(f"User Page for User ID: {user.id}")
            ui.label(f"Email: {user.email}")
            ui.button("Go to Main Page", on_click=lambda: ui.navigate.to("/"))
        return None
```

- [ ] **Step 4: Delete frontend/register.py**

```bash
rm not_dot_net/frontend/register.py
```

- [ ] **Step 5: Commit**

```bash
git add -A not_dot_net/frontend/
git commit -m "refactor: frontend pages use direct imports, login POSTs to /auth/cookie/login"
```

---

### Task 7: Fix cli.py — async call

**Files:**
- Modify: `not_dot_net/cli.py`

- [ ] **Step 1: Rewrite cli.py**

Fix `create_user` to actually run the async function. Adapt imports to new structure.

```python
import asyncio
from typing import Optional

from cyclopts import App
from yaml import safe_dump

app = App(name="NotDotNet", version="0.1.0")


@app.command
def serve(host: str = "localhost", port: int = 8000, env_file: Optional[str] = None):
    """Serve the NotDotNet application."""
    from not_dot_net.app import main
    main(host, port, env_file, reload=False)


@app.command
def create_user(username: str, password: str, env_file: Optional[str] = None):
    """Create a new user."""
    from not_dot_net.config import init_settings
    from not_dot_net.backend.db import init_db, create_db_and_tables, get_async_session, get_user_db
    from not_dot_net.backend.users import get_user_manager
    from not_dot_net.backend.schemas import UserCreate
    from contextlib import asynccontextmanager

    async def _create():
        settings = init_settings(env_file)
        init_db(settings.backend.database_url)
        await create_db_and_tables()

        get_session = asynccontextmanager(get_async_session)
        get_db = asynccontextmanager(get_user_db)
        get_mgr = asynccontextmanager(get_user_manager)

        async with get_session() as session:
            async with get_db(session) as user_db:
                async with get_mgr(user_db) as user_manager:
                    user = await user_manager.create(
                        UserCreate(
                            email=username,
                            password=password,
                            is_active=True,
                            is_superuser=False,
                        )
                    )
                    print(f"User '{user.email}' created successfully.")

    asyncio.run(_create())


@app.command
def default_config():
    """Print default configuration as YAML."""
    from not_dot_net.config import Settings
    print(safe_dump(Settings().model_dump()))


if __name__ in {"__main__", "__mp_main__"}:
    app()
```

- [ ] **Step 2: Commit**

```bash
git add not_dot_net/cli.py
git commit -m "fix: cli create_user now actually runs the async function"
```

---

### Task 8: Clean up — remove ensure_default_admin, update CLAUDE.md

**Files:**
- Modify: `not_dot_net/backend/users.py` (remove ensure_default_admin if present)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify ensure_default_admin is not referenced**

Run: `grep -r "ensure_default_admin" not_dot_net/`

If unreferenced, it was already removed when we rewrote `users.py` in Task 3.

- [ ] **Step 2: Update CLAUDE.md to reflect new structure**

- [ ] **Step 3: Run the app to smoke test**

Run: `uv run python -m not_dot_net.cli default-config`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: update CLAUDE.md, final cleanup"
```
