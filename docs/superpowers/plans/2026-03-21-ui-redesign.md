# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder intranet UI with a people directory (card grid, expandable cards, inline edit) and onboarding initiation form.

**Architecture:** Single NiceGUI page at `/` with top nav bar and tab panels (People, Onboarding). People directory uses a card grid with expandable detail/edit. Onboarding is a simple form + request list. Reuse FastAPI-Users routes by extending schemas. New `OnboardingRequest` SQLAlchemy model for the onboarding table.

**Tech Stack:** NiceGUI, FastAPI-Users, SQLAlchemy async, Tailwind CSS classes, pydantic-settings

**Spec:** `docs/superpowers/specs/2026-03-21-ui-redesign-design.md`

---

### Task 1: Extend the User model with profile fields

**Files:**
- Modify: `not_dot_net/backend/db.py:25-28`
- Modify: `not_dot_net/backend/schemas.py:1-15`
- Test: `tests/test_model.py` (create)

- [ ] **Step 1: Write failing test for new User fields**

Create `tests/test_model.py`:

```python
from not_dot_net.backend.db import User


def test_user_has_profile_fields():
    """User model has all directory profile fields."""
    for field in ("full_name", "phone", "office", "team", "title", "employment_status"):
        assert hasattr(User, field), f"User missing field: {field}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py::test_user_has_profile_fields -v`
Expected: FAIL — User has no `full_name` attribute

- [ ] **Step 3: Add profile fields to User model**

In `not_dot_net/backend/db.py`, add to the `User` class after the `auth_method` field:

```python
class User(SQLAlchemyBaseUserTableUUID, Base):
    auth_method: Mapped[AuthMethod] = mapped_column(
        SAEnum(AuthMethod), default=AuthMethod.LOCAL
    )
    full_name: Mapped[str | None] = mapped_column(default=None)
    phone: Mapped[str | None] = mapped_column(default=None)
    office: Mapped[str | None] = mapped_column(default=None)
    team: Mapped[str | None] = mapped_column(default=None)
    title: Mapped[str | None] = mapped_column(default=None)
    employment_status: Mapped[str | None] = mapped_column(default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model.py::test_user_has_profile_fields -v`
Expected: PASS

- [ ] **Step 5: Update schemas to include profile fields**

In `not_dot_net/backend/schemas.py`:

```python
import uuid
from typing import Optional

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    office: Optional[str] = None
    team: Optional[str] = None
    title: Optional[str] = None
    employment_status: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    office: Optional[str] = None
    team: Optional[str] = None
    title: Optional[str] = None
    employment_status: Optional[str] = None
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 7: Delete old dev database and commit**

```bash
rm -f test.db
git add not_dot_net/backend/db.py not_dot_net/backend/schemas.py tests/test_model.py
git commit -m "feat: add profile fields to User model and schemas"
```

---

### Task 2: Add teams list to config

**Files:**
- Modify: `not_dot_net/config.py:30-36`
- Test: `tests/test_model.py` (append)

- [ ] **Step 1: Write failing test**

Add to `tests/test_model.py`:

```python
import os
from not_dot_net.config import Settings


def test_settings_has_teams():
    """Settings has a teams list with default values."""
    # Prevent pydantic-settings from trying to read a yaml file
    s = Settings(
        jwt_secret="x" * 34,
        storage_secret="x" * 34,
        _yaml_file=None,
        _env_file=None,
    )
    assert isinstance(s.teams, list)
    assert len(s.teams) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py::test_settings_has_teams -v`
Expected: FAIL — Settings has no `teams` field

- [ ] **Step 3: Add teams field to Settings**

In `not_dot_net/config.py`, add to the `Settings` class:

```python
teams: list[str] = [
    "Plasma Physics",
    "Instrumentation",
    "Space Weather",
    "Theory & Simulation",
    "Administration",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model.py::test_settings_has_teams -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/config.py tests/test_model.py
git commit -m "feat: add teams list to Settings config"
```

---

### Task 3: Create OnboardingRequest model

**Files:**
- Create: `not_dot_net/backend/onboarding.py`
- Modify: `not_dot_net/backend/db.py` (import in `create_db_and_tables`)
- Test: `tests/test_model.py` (append)

- [ ] **Step 1: Write failing test**

Add to `tests/test_model.py`:

```python
from not_dot_net.backend.onboarding import OnboardingRequest


def test_onboarding_request_has_fields():
    """OnboardingRequest model has all required fields."""
    for field in (
        "id", "created_by", "person_name", "person_email",
        "role_status", "team", "start_date", "note",
        "status", "created_at", "updated_at",
    ):
        assert hasattr(OnboardingRequest, field), f"OnboardingRequest missing field: {field}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py::test_onboarding_request_has_fields -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create OnboardingRequest model**

Create `not_dot_net/backend/onboarding.py`:

```python
import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from not_dot_net.backend.db import Base


class OnboardingRequest(Base):
    __tablename__ = "onboarding_request"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    person_name: Mapped[str] = mapped_column(String(255))
    person_email: Mapped[str] = mapped_column(String(255))
    role_status: Mapped[str] = mapped_column(String(100))
    team: Mapped[str] = mapped_column(String(255))
    start_date: Mapped[date]
    note: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model.py::test_onboarding_request_has_fields -v`
Expected: PASS

- [ ] **Step 5: Register model in create_db_and_tables**

In `not_dot_net/backend/db.py`, update `create_db_and_tables()` to import the onboarding model so it's registered with `Base.metadata`:

```python
async def create_db_and_tables() -> None:
    if _engine is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    import not_dot_net.backend.onboarding  # noqa: F401 — register model with Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
rm -f test.db
git add not_dot_net/backend/onboarding.py not_dot_net/backend/db.py tests/test_model.py
git commit -m "feat: add OnboardingRequest model"
```

---

### Task 4: Create onboarding API router

**Files:**
- Create: `not_dot_net/backend/onboarding_router.py`
- Modify: `not_dot_net/app.py` (add router include)
- Test: `tests/test_onboarding_api.py` (create)

- [ ] **Step 1: Write failing test for POST /api/onboarding**

Create `tests/test_onboarding_api.py`. Use `httpx.AsyncClient` with the NiceGUI `app` as ASGI transport. Use a `conftest.py`-level fixture or inline fixture that resets the DB to a tmp path before each test. Since NiceGUI's test plugin manages the app lifecycle, we avoid calling `create_app()` again — instead, just override the DB engine in the fixture:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from nicegui import app

from not_dot_net.backend.db import Base
from not_dot_net.backend.users import authenticate_and_get_token


@pytest.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Override DB to use a fresh temp database for each test."""
    from not_dot_net.backend import db
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    old_engine, old_session = db._engine, db._async_session_maker
    db._engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    db._async_session_maker = async_sessionmaker(db._engine, expire_on_commit=False)
    import not_dot_net.backend.onboarding  # noqa: F401
    async with db._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from not_dot_net.backend.users import ensure_default_admin
    await ensure_default_admin()
    yield
    await db._engine.dispose()
    db._engine, db._async_session_maker = old_engine, old_session


async def _get_auth_header():
    token = await authenticate_and_get_token("admin@not-dot-net.dev", "admin")
    return {"Cookie": f"fastapiusersauth={token}"}


async def test_create_onboarding_request():
    headers = await _get_auth_header()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/onboarding",
            json={
                "person_name": "Jane Doe",
                "person_email": "jane@lpp.fr",
                "role_status": "PhD student",
                "team": "Plasma Physics",
                "start_date": "2026-09-01",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["person_name"] == "Jane Doe"
        assert data["status"] == "pending"


async def test_list_onboarding_requests():
    headers = await _get_auth_header()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/onboarding",
            json={
                "person_name": "Jane Doe",
                "person_email": "jane@lpp.fr",
                "role_status": "PhD student",
                "team": "Plasma Physics",
                "start_date": "2026-09-01",
            },
            headers=headers,
        )
        resp = await client.get("/api/onboarding", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_api.py -v`
Expected: FAIL — 404 on `/api/onboarding`

- [ ] **Step 3: Create onboarding router**

Create `not_dot_net/backend/onboarding_router.py`:

```python
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from not_dot_net.backend.db import User, get_async_session
from not_dot_net.backend.onboarding import OnboardingRequest
from not_dot_net.backend.users import current_active_user

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingCreate(BaseModel):
    person_name: str
    person_email: EmailStr
    role_status: str
    team: str
    start_date: date
    note: Optional[str] = None


class OnboardingRead(BaseModel):
    id: uuid.UUID
    created_by: Optional[uuid.UUID]
    person_name: str
    person_email: str
    role_status: str
    team: str
    start_date: date
    note: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=OnboardingRead, status_code=201)
async def create_onboarding_request(
    data: OnboardingCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    request = OnboardingRequest(
        created_by=user.id,
        person_name=data.person_name,
        person_email=data.person_email,
        role_status=data.role_status,
        team=data.team,
        start_date=data.start_date,
        note=data.note,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


@router.get("", response_model=list[OnboardingRead])
async def list_onboarding_requests(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    if user.is_superuser:
        stmt = select(OnboardingRequest).order_by(OnboardingRequest.created_at.desc())
    else:
        stmt = (
            select(OnboardingRequest)
            .where(OnboardingRequest.created_by == user.id)
            .order_by(OnboardingRequest.created_at.desc())
        )
    result = await session.execute(stmt)
    return result.scalars().all()
```

- [ ] **Step 4: Register router in app.py**

In `not_dot_net/app.py`, add import:

```python
from not_dot_net.backend.onboarding_router import router as onboarding_router
```

And in `create_app()`, after `app.include_router(auth_router)`:

```python
app.include_router(onboarding_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_onboarding_api.py -v`
Expected: PASS

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
rm -f test.db
git add not_dot_net/backend/onboarding_router.py not_dot_net/app.py tests/test_onboarding_api.py
git commit -m "feat: add onboarding API router (POST + GET)"
```

---

### Task 5: Build the app shell (header + tabs)

**Files:**
- Modify: `not_dot_net/app.py:45-71` (replace `main_page`)
- Create: `not_dot_net/frontend/shell.py`
- Remove: `not_dot_net/frontend/user_page.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_login.py`:

```python
async def test_main_page_redirects_when_unauthenticated(user: User) -> None:
    await user.open("/")
    await user.should_see("Log in")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_login.py::test_main_page_redirects_when_unauthenticated -v`
Expected: FAIL — current main page has no auth check, shows "Content of A"

- [ ] **Step 3: Create shell module**

Create `not_dot_net/frontend/shell.py`:

```python
from typing import Optional

from fastapi import Depends
from fastapi.responses import RedirectResponse
from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.users import current_active_user_optional


def setup():
    @ui.page("/")
    def main_page(
        user: Optional[User] = Depends(current_active_user_optional),
    ) -> Optional[RedirectResponse]:
        if not user:
            return RedirectResponse("/login")

        with ui.header().classes("row items-center justify-between px-4"):
            ui.label("LPP Intranet").classes("text-h6 text-white")
            with ui.tabs().classes("ml-4") as tabs:
                ui.tab("People", icon="people")
                ui.tab("Onboarding", icon="person_add")
            with ui.row().classes("items-center"):
                with ui.button(icon="person").props("flat color=white"):
                    with ui.menu():
                        ui.menu_item("My Profile", on_click=lambda: _go_to_profile(tabs))
                        ui.menu_item("Logout", on_click=lambda: _logout())

        with ui.tab_panels(tabs, value="People").classes("w-full"):
            with ui.tab_panel("People"):
                ui.label("People directory placeholder")
            with ui.tab_panel("Onboarding"):
                ui.label("Onboarding placeholder")

        return None


def _go_to_profile(tabs):
    """Switch to People tab — the directory will expand the user's own card."""
    tabs.set_value("People")


def _logout():
    ui.run_javascript(
        'document.cookie = "fastapiusersauth=; path=/; max-age=0";'
        'window.location.href = "/login";'
    )
```

- [ ] **Step 4: Update app.py to use shell instead of inline main_page**

Replace the `main_page` function and imports in `not_dot_net/app.py`. Remove the `@ui.page("/")` main_page function (lines 45-71). Add shell setup. The resulting `app.py` should look like:

```python
from typing import Optional

from nicegui import app, ui

from not_dot_net.config import init_settings
from not_dot_net.backend.db import init_db, create_db_and_tables
from not_dot_net.backend.users import fastapi_users, jwt_backend, cookie_backend, ensure_default_admin
from not_dot_net.backend.schemas import UserRead, UserUpdate
from not_dot_net.backend.auth import router as auth_router
from not_dot_net.backend.onboarding_router import router as onboarding_router
from not_dot_net.frontend.login import setup as setup_login
from not_dot_net.frontend.shell import setup as setup_shell


def create_app(config_file: str | None = None):
    settings = init_settings(config_file)
    init_db(settings.backend.database_url)

    async def startup():
        await create_db_and_tables()
        await ensure_default_admin()

    app.on_startup(startup)

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
    app.include_router(onboarding_router)

    setup_login()
    setup_shell()


def main(
    host: str = "localhost",
    port: int = 8088,
    env_file: Optional[str] = None,
    reload=False,
) -> None:
    create_app(env_file)
    from not_dot_net.config import get_settings
    ui.run(
        storage_secret=get_settings().storage_secret,
        host=host, port=port, reload=reload, title="NotDotNet",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main("localhost", 8088, None)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_login.py -v`
Expected: PASS

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
rm -f test.db
git add not_dot_net/frontend/shell.py not_dot_net/app.py tests/test_login.py
git rm not_dot_net/frontend/user_page.py
git commit -m "feat: replace placeholder main page with app shell (header + tabs)"
```

---

### Task 6: Build the people directory (card grid + search)

**Files:**
- Create: `not_dot_net/frontend/directory.py`
- Modify: `not_dot_net/frontend/shell.py` (replace People tab placeholder)

- [ ] **Step 1: Write failing test**

Create `tests/test_directory.py`:

```python
from nicegui.testing import User


async def test_directory_shows_search(user: User) -> None:
    await user.open("/login")
    user.find("Email").type("admin@not-dot-net.dev")
    user.find("Password").type("admin")
    user.find("Log in").click()
    await user.open("/")
    await user.should_see("Search")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_directory.py::test_directory_shows_search -v`
Expected: FAIL — "Search" not found

- [ ] **Step 3: Create directory module**

Create `not_dot_net/frontend/directory.py`. Key design points:
- Use `expanded_card_id` dict as single source of truth for which card is expanded
- Use `UserManager` for edit/delete operations (not raw SQL) via the same `asynccontextmanager` escape hatch pattern used in `authenticate_and_get_token`
- Iterate children via `card_container.default_slot.children` not `card_container`

```python
from contextlib import asynccontextmanager

from nicegui import ui

from not_dot_net.backend.db import User, get_async_session, get_user_db
from not_dot_net.backend.users import get_user_manager
from not_dot_net.backend.schemas import UserUpdate
from sqlalchemy import select


async def _load_people() -> list[User]:
    get_session_ctx = asynccontextmanager(get_async_session)
    async with get_session_ctx() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        return result.scalars().all()


async def _update_user(user_id, updates: dict):
    """Update a user via UserManager (respects FastAPI-Users hooks)."""
    get_session_ctx = asynccontextmanager(get_async_session)
    get_user_db_ctx = asynccontextmanager(get_user_db)
    get_user_manager_ctx = asynccontextmanager(get_user_manager)
    async with get_session_ctx() as session:
        async with get_user_db_ctx(session) as user_db:
            async with get_user_manager_ctx(user_db) as manager:
                user = await manager.get(user_id)
                update_schema = UserUpdate(**updates)
                await manager.update(update_schema, user)


async def _delete_user(user_id):
    """Delete a user via UserManager (respects FastAPI-Users hooks)."""
    get_session_ctx = asynccontextmanager(get_async_session)
    get_user_db_ctx = asynccontextmanager(get_user_db)
    get_user_manager_ctx = asynccontextmanager(get_user_manager)
    async with get_session_ctx() as session:
        async with get_user_db_ctx(session) as user_db:
            async with get_user_manager_ctx(user_db) as manager:
                user = await manager.get(user_id)
                await manager.delete(user)


def render(current_user: User):
    search = ui.input(placeholder="Search by name, team, office, email...").props(
        "outlined dense"
    ).classes("w-full mb-4")

    card_container = ui.element("div").classes(
        "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 w-full"
    )

    # Shared state: which card is currently expanded (by person id), and
    # a registry of detail containers keyed by person id for collapse logic
    state = {"expanded_id": None, "details": {}}

    async def refresh():
        people = await _load_people()
        state["expanded_id"] = None
        state["details"] = {}
        card_container.clear()
        with card_container:
            for person in people:
                _person_card(person, current_user, state)

    def filter_cards():
        query = search.value.lower() if search.value else ""
        for child in card_container.default_slot.children:
            if hasattr(child, "_person_search_text"):
                child.set_visibility(query in child._person_search_text)

    search.on("update:model-value", lambda: filter_cards())

    ui.timer(0, refresh, once=True)


def _person_card(person: User, current_user: User, state: dict):
    display_name = person.full_name or person.email
    search_text = " ".join(
        s.lower() for s in [
            person.full_name or "", person.email,
            person.team or "", person.office or "",
        ]
    )

    with ui.card().classes("cursor-pointer") as card:
        card._person_search_text = search_text

        with ui.row().classes("items-center gap-3"):
            ui.icon("person", size="xl").classes(
                "rounded-full bg-gray-200 p-2"
            )
            with ui.column().classes("gap-0"):
                ui.label(display_name).classes("font-bold")
                if person.team:
                    ui.label(person.team).classes("text-sm text-gray-500")
                if person.office:
                    ui.label(f"Office {person.office}").classes("text-sm text-gray-500")

        detail_container = ui.column().classes("w-full mt-2")
        detail_container.set_visibility(False)
        state["details"][person.id] = detail_container

        def toggle_expand():
            currently_expanded = state["expanded_id"]
            if currently_expanded == person.id:
                detail_container.set_visibility(False)
                state["expanded_id"] = None
            else:
                if currently_expanded and currently_expanded in state["details"]:
                    state["details"][currently_expanded].set_visibility(False)
                detail_container.set_visibility(True)
                state["expanded_id"] = person.id
                _render_detail(detail_container, person, current_user, state)

        card.on("click", toggle_expand)


def _render_detail(container, person: User, current_user: User, state: dict):
    container.clear()
    is_own = person.id == current_user.id
    is_admin = current_user.is_superuser

    with container:
        ui.separator()
        if person.phone:
            ui.label(f"Phone: {person.phone}").classes("text-sm")
        ui.label(f"Email: {person.email}").classes("text-sm")
        if person.employment_status:
            ui.label(f"Status: {person.employment_status}").classes("text-sm")
        if person.title:
            ui.label(f"Title: {person.title}").classes("text-sm")

        if is_own or is_admin:
            ui.button("Edit", icon="edit", on_click=lambda: _render_edit(
                container, person, current_user, state
            )).props("flat dense")

        if is_admin and not is_own:
            with ui.dialog() as confirm_dialog, ui.card():
                ui.label(f"Delete {person.full_name or person.email}?")
                with ui.row():
                    ui.button("Cancel", on_click=confirm_dialog.close).props("flat")

                    async def do_delete():
                        confirm_dialog.close()
                        await _delete_user(person.id)
                        ui.notify(
                            f"Deleted {person.full_name or person.email}",
                            color="positive",
                        )
                        container.parent_slot.parent.set_visibility(False)

                    ui.button("Delete", on_click=do_delete).props(
                        "flat color=negative"
                    )

            ui.button("Delete", icon="delete", on_click=confirm_dialog.open).props(
                "flat dense color=negative"
            )


def _render_edit(container, person: User, current_user: User, state: dict):
    container.clear()
    is_admin = current_user.is_superuser

    with container:
        ui.separator()

        fields = {}
        if is_admin:
            fields["full_name"] = ui.input(
                "Full Name", value=person.full_name or ""
            ).props("outlined dense")
            fields["email"] = ui.input(
                "Email", value=person.email
            ).props("outlined dense")
            fields["team"] = ui.input(
                "Team", value=person.team or ""
            ).props("outlined dense")
            fields["employment_status"] = ui.input(
                "Status", value=person.employment_status or ""
            ).props("outlined dense")
            fields["title"] = ui.input(
                "Title", value=person.title or ""
            ).props("outlined dense")

        fields["phone"] = ui.input(
            "Phone", value=person.phone or ""
        ).props("outlined dense")
        fields["office"] = ui.input(
            "Office", value=person.office or ""
        ).props("outlined dense")

        async def save():
            updates = {k: (v.value or None) for k, v in fields.items()}
            await _update_user(person.id, updates)
            ui.notify("Saved", color="positive")
            # Refresh person data and re-render detail view
            people = await _load_people()
            updated = next((p for p in people if p.id == person.id), person)
            _render_detail(container, updated, current_user, state)

        with ui.row():
            ui.button("Save", on_click=save).props("flat dense color=primary")
            ui.button("Cancel", on_click=lambda: _render_detail(
                container, person, current_user, state
            )).props("flat dense")
```

- [ ] **Step 4: Wire directory into shell**

In `not_dot_net/frontend/shell.py`, add import:

```python
from not_dot_net.frontend.directory import render as render_directory
```

Replace the People tab panel content:

```python
with ui.tab_panel("People"):
    render_directory(user)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_directory.py -v`
Expected: PASS

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
rm -f test.db
git add not_dot_net/frontend/directory.py not_dot_net/frontend/shell.py tests/test_directory.py
git commit -m "feat: add people directory with card grid, search, expand/edit"
```

---

### Task 7: Build the onboarding tab

**Files:**
- Create: `not_dot_net/frontend/onboarding.py`
- Modify: `not_dot_net/frontend/shell.py` (replace Onboarding tab placeholder)

- [ ] **Step 1: Write failing test**

Create `tests/test_onboarding_ui.py`:

```python
from nicegui.testing import User


async def test_onboarding_tab_shows_form(user: User) -> None:
    await user.open("/login")
    user.find("Email").type("admin@not-dot-net.dev")
    user.find("Password").type("admin")
    user.find("Log in").click()
    await user.open("/")
    user.find("Onboarding").click()
    await user.should_see("New Person")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboarding_ui.py -v`
Expected: FAIL — "New Person" not found

- [ ] **Step 3: Create onboarding UI module**

Create `not_dot_net/frontend/onboarding.py`. This module calls the API endpoints from Task 4 instead of doing direct DB queries, keeping the permission logic in one place:

```python
from datetime import date

from nicegui import ui
from httpx import AsyncClient, ASGITransport
from nicegui import app as nicegui_app

from not_dot_net.backend.db import User
from not_dot_net.config import get_settings


async def _api_post(path: str, json: dict, cookie: str) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=nicegui_app), base_url="http://localhost"
    ) as client:
        resp = await client.post(path, json=json, cookies={"fastapiusersauth": cookie})
        resp.raise_for_status()
        return resp.json()


async def _api_get(path: str, cookie: str) -> list:
    async with AsyncClient(
        transport=ASGITransport(app=nicegui_app), base_url="http://localhost"
    ) as client:
        resp = await client.get(path, cookies={"fastapiusersauth": cookie})
        resp.raise_for_status()
        return resp.json()


def render(current_user: User):
    ui.label("New Person").classes("text-h6 mb-2")

    settings = get_settings()
    team_options = settings.teams
    status_options = ["Researcher", "PhD student", "Intern", "Visitor"]

    name_input = ui.input("Name").props("outlined dense").classes("w-full")
    email_input = ui.input("Email").props("outlined dense").classes("w-full")
    role_select = ui.select(status_options, label="Role / Status").props(
        "outlined dense"
    ).classes("w-full")
    team_select = ui.select(team_options, label="Team").props(
        "outlined dense"
    ).classes("w-full")
    date_input = ui.date(value=date.today().isoformat()).classes("w-full")
    note_input = ui.textarea("Note (optional)").props("outlined dense").classes("w-full")

    request_list = ui.column().classes("w-full mt-4")

    def _get_cookie() -> str:
        """Get the auth cookie from the current NiceGUI client storage."""
        from nicegui import app
        return app.storage.browser.get("fastapiusersauth", "")

    async def refresh_list():
        try:
            requests = await _api_get("/api/onboarding", _get_cookie())
        except Exception:
            requests = []
        request_list.clear()
        with request_list:
            if not requests:
                ui.label("No onboarding requests yet.").classes("text-gray-500")
                return
            ui.label("Onboarding Requests").classes("text-h6 mt-2")
            for req in requests:
                with ui.card().classes("w-full"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(
                            f"{req['person_name']} ({req['person_email']})"
                        ).classes("font-bold")
                        ui.badge(req["status"]).props(
                            "color=orange"
                            if req["status"] == "pending"
                            else "color=green"
                        )
                    ui.label(
                        f"{req['role_status']} · {req['team']} · starts {req['start_date']}"
                    ).classes("text-sm text-gray-500")
                    if req.get("note"):
                        ui.label(req["note"]).classes("text-sm")

    async def submit():
        if not name_input.value or not email_input.value:
            ui.notify("Name and email are required", color="negative")
            return
        try:
            await _api_post(
                "/api/onboarding",
                {
                    "person_name": name_input.value,
                    "person_email": email_input.value,
                    "role_status": role_select.value or "",
                    "team": team_select.value or "",
                    "start_date": date_input.value
                    if date_input.value
                    else date.today().isoformat(),
                    "note": note_input.value or None,
                },
                _get_cookie(),
            )
        except Exception:
            ui.notify("Failed to create request", color="negative")
            return

        ui.notify("Onboarding request created", color="positive")
        name_input.value = ""
        email_input.value = ""
        role_select.value = None
        team_select.value = None
        note_input.value = ""
        await refresh_list()

    ui.button("Submit", on_click=submit, icon="send").props("color=primary").classes(
        "mt-2"
    )

    ui.timer(0, refresh_list, once=True)
```

**Note:** The `_api_post`/`_api_get` helpers call the FastAPI endpoints via ASGI transport (in-process, no network). This avoids duplicating the permission logic from the router. If this approach proves problematic in NiceGUI's context, fall back to direct DB queries as a pragmatic alternative — the filtering logic is simple and unlikely to drift.

- [ ] **Step 4: Wire onboarding into shell**

In `not_dot_net/frontend/shell.py`, add import:

```python
from not_dot_net.frontend.onboarding import render as render_onboarding
```

Replace the Onboarding tab panel content:

```python
with ui.tab_panel("Onboarding"):
    render_onboarding(user)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_onboarding_ui.py -v`
Expected: PASS

- [ ] **Step 6: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
rm -f test.db
git add not_dot_net/frontend/onboarding.py not_dot_net/frontend/shell.py tests/test_onboarding_ui.py
git commit -m "feat: add onboarding tab with form and request list"
```

---

### Task 8: Refresh the login page

**Files:**
- Modify: `not_dot_net/frontend/login.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_login.py`:

```python
async def test_login_page_shows_app_title(user: User) -> None:
    await user.open("/login")
    await user.should_see("LPP Intranet")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_login.py::test_login_page_shows_app_title -v`
Expected: FAIL — "LPP Intranet" not found

- [ ] **Step 3: Update login page**

Replace `not_dot_net/frontend/login.py` entirely:

```python
from typing import Optional

from fastapi.responses import RedirectResponse
from nicegui import app, ui

from not_dot_net.backend.users import authenticate_and_get_token


def setup():
    @ui.page("/login")
    def login(redirect_to: str = "/") -> Optional[RedirectResponse]:
        if app.storage.user.get("authenticated", False):
            return RedirectResponse(redirect_to)

        async def try_login() -> None:
            try:
                token = await authenticate_and_get_token(email.value, password.value)
                if token is None:
                    ui.notify("Invalid email or password", color="negative")
                    return

                ui.run_javascript(
                    f'document.cookie = "fastapiusersauth={token}; path=/; SameSite=Lax";'
                    f'window.location.href = "{redirect_to}";'
                )
            except Exception:
                ui.notify("Auth server error", color="negative")

        with ui.column().classes("absolute-center items-center gap-4"):
            ui.label("LPP Intranet").classes("text-h4 text-weight-light")
            with ui.card().classes("w-80"):
                email = ui.input("Email").props("outlined dense").classes(
                    "w-full"
                ).on("keydown.enter", try_login)
                password = ui.input(
                    "Password", password=True, password_toggle_button=True
                ).props("outlined dense").classes("w-full").on(
                    "keydown.enter", try_login
                )
                ui.button("Log in", on_click=try_login).classes("w-full")
        return None
```

Note: default `redirect_to` changed from `/user/profile` to `/`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_login.py -v`
Expected: All login tests PASS

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/login.py tests/test_login.py
git commit -m "feat: refresh login page with app title and cleaner styling"
```

---

### Task 9: Clean up and final verification

**Files:**
- Verify: `not_dot_net/frontend/user_page.py` is removed (done in Task 5)
- Verify: `not_dot_net/app.py` has no stale imports

- [ ] **Step 1: Verify user_page.py is removed and no stale imports**

Run: `grep -r "user_page" not_dot_net/`
Expected: No results

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 3: Manual smoke test**

Run: `uv run python -m not_dot_net.cli serve --port 8088`

Verify in browser:
- `/login` shows "LPP Intranet" title + clean login card
- After login, `/` shows header with People and Onboarding tabs
- User menu shows "My Profile" and "Logout"
- People tab shows search bar and admin user card
- Clicking card expands to show details + edit button
- Edit mode allows changing phone/office, save works
- Onboarding tab shows form, submitting creates a request in the list
- Logout works

- [ ] **Step 4: Commit if any cleanup was needed**

```bash
rm -f test.db
git add not_dot_net/ tests/
git commit -m "chore: final cleanup for UI redesign"
```
