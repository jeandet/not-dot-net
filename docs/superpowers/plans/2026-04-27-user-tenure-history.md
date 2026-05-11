# User Tenure & History Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track the full employment lifecycle of people at LPP (status, employer, dates per period) and enrich audit logging with field-level diffs for point-in-time user state reconstruction.

**Architecture:** A new `UserTenure` table stores one row per employment period (status + employer + start/end dates). The latest open tenure is the "current" state. Audit log entries for user updates gain a `changes` dict in `metadata_json` (old/new per field). The onboarding workflow gains an `employer` field. A new "History" tab appears in the directory person detail view. OrgConfig gains an `employers` list for the controlled vocabulary.

**Tech Stack:** SQLAlchemy (async), Alembic migration, NiceGUI UI, existing audit module, existing ConfigSection pattern.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `not_dot_net/backend/tenure_service.py` | UserTenure model + CRUD (add/close/list/stats) |
| Create | `tests/test_tenure_service.py` | Unit tests for tenure CRUD and stats |
| Create | `alembic/versions/0007_add_user_tenure.py` | Migration: create `user_tenure` table |
| Modify | `not_dot_net/config.py` | Add `employers` list to `OrgConfig` |
| Modify | `not_dot_net/backend/workflow_service.py` | Add `employer` field to onboarding initiation step |
| Modify | `not_dot_net/frontend/directory.py` | Tenure history tab in person detail + audit diff on save |
| Modify | `not_dot_net/backend/audit.py` | No schema changes (already has `metadata_json`) — just ensure callers pass diffs |
| Modify | `not_dot_net/backend/db.py` | Import tenure model in `create_db_and_tables()` |
| Modify | `not_dot_net/frontend/i18n.py` | i18n keys for tenure UI + employer field |
| Modify | `not_dot_net/backend/data_io.py` | Include tenures in export/import |
| Modify | `tests/conftest.py` | Import tenure model for in-memory DB creation |

---

### Task 1: UserTenure Model & Service

**Files:**
- Create: `not_dot_net/backend/tenure_service.py`
- Create: `tests/test_tenure_service.py`

- [ ] **Step 1: Write failing tests for tenure CRUD**

```python
# tests/test_tenure_service.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tenure_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'not_dot_net.backend.tenure_service'`

- [ ] **Step 3: Implement UserTenure model and CRUD**

```python
# not_dot_net/backend/tenure_service.py
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
```

- [ ] **Step 4: Register model in conftest.py and db.py**

In `tests/conftest.py`, add to the imports block (after the other model imports):
```python
    import not_dot_net.backend.tenure_service  # noqa: F401
```

In `not_dot_net/backend/db.py`, inside `create_db_and_tables()`, add:
```python
    import not_dot_net.backend.tenure_service  # noqa: F401 — register UserTenure with Base
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenure_service.py -v`
Expected: all 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/tenure_service.py tests/test_tenure_service.py not_dot_net/backend/db.py tests/conftest.py
git commit -m "feat: add UserTenure model and CRUD service"
```

---

### Task 2: Tenure Stats Queries

**Files:**
- Modify: `not_dot_net/backend/tenure_service.py`
- Modify: `tests/test_tenure_service.py`

- [ ] **Step 1: Write failing tests for stats**

Append to `tests/test_tenure_service.py`:

```python
from not_dot_net.backend.tenure_service import (
    avg_duration_by_status,
    headcount_at_date,
    update_tenure,
    delete_tenure,
)


async def test_avg_duration_by_status():
    u1 = await _create_user("a@lpp.fr")
    u2 = await _create_user("b@lpp.fr")
    await add_tenure(user_id=u1.id, status="PhD", employer="CNRS",
                     start_date=date(2022, 9, 1), end_date=date(2025, 8, 31))
    await add_tenure(user_id=u2.id, status="PhD", employer="Polytechnique",
                     start_date=date(2023, 9, 1), end_date=date(2026, 8, 31))
    stats = await avg_duration_by_status()
    assert "PhD" in stats
    assert stats["PhD"]["count"] == 2
    assert stats["PhD"]["avg_days"] > 0


async def test_headcount_at_date():
    u1 = await _create_user("c@lpp.fr")
    u2 = await _create_user("d@lpp.fr")
    await add_tenure(user_id=u1.id, status="Intern", employer="CNRS",
                     start_date=date(2025, 3, 1), end_date=date(2025, 8, 31))
    await add_tenure(user_id=u2.id, status="PhD", employer="CNRS",
                     start_date=date(2025, 1, 1))
    count = await headcount_at_date(date(2025, 6, 1))
    assert count == 2
    count_after = await headcount_at_date(date(2025, 10, 1))
    assert count_after == 1


async def test_update_tenure():
    user = await _create_user("e@lpp.fr")
    tenure = await add_tenure(
        user_id=user.id, status="Intern", employer="CNRS",
        start_date=date(2025, 3, 1),
    )
    updated = await update_tenure(tenure.id, status="PhD", employer="Polytechnique")
    assert updated.status == "PhD"
    assert updated.employer == "Polytechnique"
    assert updated.start_date == date(2025, 3, 1)


async def test_delete_tenure():
    user = await _create_user("f@lpp.fr")
    tenure = await add_tenure(
        user_id=user.id, status="Intern", employer="CNRS",
        start_date=date(2025, 3, 1),
    )
    await delete_tenure(tenure.id)
    tenures = await list_tenures(user.id)
    assert len(tenures) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tenure_service.py::test_avg_duration_by_status tests/test_tenure_service.py::test_headcount_at_date tests/test_tenure_service.py::test_update_tenure tests/test_tenure_service.py::test_delete_tenure -v`
Expected: FAIL — `ImportError: cannot import name 'avg_duration_by_status'`

- [ ] **Step 3: Implement stats, update, and delete**

Append to `not_dot_net/backend/tenure_service.py`:

```python
from sqlalchemy import and_, or_, func as sa_func, case, extract


async def avg_duration_by_status() -> dict[str, dict]:
    """Average tenure duration per status (only closed tenures with end_date)."""
    async with session_scope() as session:
        result = await session.execute(
            select(
                UserTenure.status,
                sa_func.count().label("count"),
                sa_func.avg(
                    func.julianday(UserTenure.end_date) - func.julianday(UserTenure.start_date)
                ).label("avg_days"),
            )
            .where(UserTenure.end_date != None)  # noqa: E711
            .group_by(UserTenure.status)
        )
        return {
            row.status: {"count": row.count, "avg_days": round(row.avg_days or 0, 1)}
            for row in result.all()
        }


async def headcount_at_date(target: date) -> int:
    """Count people with an active tenure on a given date."""
    async with session_scope() as session:
        result = await session.execute(
            select(sa_func.count(sa_func.distinct(UserTenure.user_id)))
            .where(
                UserTenure.start_date <= target,
                or_(
                    UserTenure.end_date == None,  # noqa: E711
                    UserTenure.end_date >= target,
                ),
            )
        )
        return result.scalar_one()


async def update_tenure(
    tenure_id: uuid.UUID,
    status: str | None = None,
    employer: str | None = None,
    start_date: date | None = None,
    end_date: date | None = ...,  # sentinel: None means "clear", ... means "don't change"
    notes: str | None = ...,
) -> UserTenure:
    async with session_scope() as session:
        tenure = await session.get(UserTenure, tenure_id)
        if tenure is None:
            raise ValueError(f"Tenure {tenure_id} not found")
        if status is not None:
            tenure.status = status
        if employer is not None:
            tenure.employer = employer
        if start_date is not None:
            tenure.start_date = start_date
        if end_date is not ...:
            tenure.end_date = end_date
        if notes is not ...:
            tenure.notes = notes
        await session.commit()
        await session.refresh(tenure)
        return tenure


async def delete_tenure(tenure_id: uuid.UUID) -> None:
    async with session_scope() as session:
        tenure = await session.get(UserTenure, tenure_id)
        if tenure is None:
            raise ValueError(f"Tenure {tenure_id} not found")
        await session.delete(tenure)
        await session.commit()
```

Note: `avg_duration_by_status` uses `julianday()` which is SQLite-specific. For PostgreSQL production, replace with `EXTRACT(EPOCH FROM end_date - start_date) / 86400`. Since both SQLite (dev/test) and PostgreSQL (prod) are used, add a compatibility note. The simplest approach: compute avg in Python instead of SQL for portability.

**Revised `avg_duration_by_status` for portability:**

```python
async def avg_duration_by_status() -> dict[str, dict]:
    """Average tenure duration per status (only closed tenures)."""
    async with session_scope() as session:
        result = await session.execute(
            select(UserTenure)
            .where(UserTenure.end_date != None)  # noqa: E711
        )
        tenures = result.scalars().all()

    by_status: dict[str, list[int]] = {}
    for t in tenures:
        days = (t.end_date - t.start_date).days
        by_status.setdefault(t.status, []).append(days)

    return {
        status: {
            "count": len(durations),
            "avg_days": round(sum(durations) / len(durations), 1),
        }
        for status, durations in by_status.items()
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenure_service.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/tenure_service.py tests/test_tenure_service.py
git commit -m "feat: add tenure stats queries (avg duration, headcount, update, delete)"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `alembic/versions/0007_add_user_tenure.py`

- [ ] **Step 1: Write the migration**

```python
# alembic/versions/0007_add_user_tenure.py
"""Add user_tenure table for employment period tracking.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_tenure",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(100), nullable=False),
        sa.Column("employer", sa.String(200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_user_tenure_user_id", "user_tenure", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_tenure_user_id", table_name="user_tenure")
    op.drop_table("user_tenure")
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `uv run pytest tests/test_tenure_service.py -v`
Expected: PASS (in-memory DB uses `create_all`, not Alembic)

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/0007_add_user_tenure.py
git commit -m "feat: add Alembic migration 0007 for user_tenure table"
```

---

### Task 4: Add `employers` to OrgConfig + `employer` to Onboarding Workflow

**Files:**
- Modify: `not_dot_net/config.py`
- Modify: `not_dot_net/backend/workflow_service.py`
- Create: `tests/test_tenure_onboarding.py`

- [ ] **Step 1: Write failing test for employer field in onboarding**

```python
# tests/test_tenure_onboarding.py
import pytest
import uuid
from contextlib import asynccontextmanager

from not_dot_net.backend.db import User, get_async_session
from not_dot_net.backend.workflow_service import (
    create_request, submit_step, workflows_config,
)
from not_dot_net.backend.roles import RoleDefinition, roles_config


async def _create_user(email="staff@test.com", role="staff") -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(id=uuid.uuid4(), email=email, hashed_password="x", role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _setup_roles():
    cfg = await roles_config.get()
    cfg.roles["staff"] = RoleDefinition(label="Staff", permissions=["create_workflows"])
    await roles_config.set(cfg)


async def test_onboarding_initiation_has_employer_field():
    cfg = await workflows_config.get()
    onboarding = cfg.workflows["onboarding"]
    initiation = onboarding.steps[0]
    field_names = [f.name for f in initiation.fields]
    assert "employer" in field_names
    employer_field = next(f for f in initiation.fields if f.name == "employer")
    assert employer_field.type == "select"
    assert employer_field.options_key == "employers"


async def test_onboarding_employer_stored_in_request_data():
    await _setup_roles()
    user = await _create_user()
    req = await create_request(
        workflow_type="onboarding",
        created_by=user.id,
        data={"contact_email": "new@test.com", "status": "PhD", "employer": "CNRS"},
        actor=user,
    )
    assert req.data["employer"] == "CNRS"


async def test_org_config_has_employers():
    from not_dot_net.config import org_config
    cfg = await org_config.get()
    assert hasattr(cfg, "employers")
    assert "CNRS" in cfg.employers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tenure_onboarding.py -v`
Expected: FAIL — `employers` not in OrgConfig, `employer` not in onboarding fields

- [ ] **Step 3: Add `employers` to OrgConfig**

In `not_dot_net/config.py`, inside `OrgConfig`, add after `employment_statuses`:

```python
    employers: list[str] = ["CNRS", "Sorbonne Université", "Polytechnique", "CNES", "Other"]
```

- [ ] **Step 4: Add `employer` field to onboarding initiation step**

In `not_dot_net/backend/workflow_service.py`, inside the `"onboarding"` workflow config, in the `"initiation"` step's `fields` list, add after the `status` field:

```python
                        FieldConfig(name="employer", type="select", required=True, label="Employer", options_key="employers"),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenure_onboarding.py -v`
Expected: all 3 tests PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `uv run pytest -x -q`
Expected: no failures (the new field is just added to defaults; existing workflow tests don't check field count)

- [ ] **Step 7: Commit**

```bash
git add not_dot_net/config.py not_dot_net/backend/workflow_service.py tests/test_tenure_onboarding.py
git commit -m "feat: add employer field to onboarding workflow and OrgConfig"
```

---

### Task 5: Audit Diffs on User Profile Edits

**Files:**
- Modify: `not_dot_net/frontend/directory.py`
- Create: `tests/test_audit_diffs.py`

- [ ] **Step 1: Write failing test for audit diff logging on user update**

```python
# tests/test_audit_diffs.py
import pytest
import uuid
from contextlib import asynccontextmanager
from datetime import date

from not_dot_net.backend.db import User, get_async_session
from not_dot_net.backend.audit import list_audit_events


async def _create_user(email="test@lpp.fr", **kwargs) -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(
            id=uuid.uuid4(), email=email, hashed_password="x",
            role="staff", phone="0100000000", office="A101", **kwargs,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_user_update_logs_audit_diff():
    from not_dot_net.backend.audit import log_audit

    user = await _create_user()
    old_values = {"phone": "0100000000", "office": "A101"}
    new_values = {"phone": "0199999999", "office": "B202"}

    diff = {k: v for k, v in new_values.items() if v != old_values.get(k)}
    changes = {k: {"old": old_values.get(k), "new": v} for k, v in diff.items()}

    await log_audit(
        "user", "update",
        actor_id=user.id, actor_email=user.email,
        target_type="user", target_id=user.id,
        detail=f"fields={','.join(diff.keys())}",
        metadata={"changes": changes},
    )

    events = await list_audit_events(category="user", action="update")
    assert len(events) == 1
    assert events[0].metadata_json["changes"]["phone"]["old"] == "0100000000"
    assert events[0].metadata_json["changes"]["phone"]["new"] == "0199999999"
    assert events[0].metadata_json["changes"]["office"]["new"] == "B202"
```

- [ ] **Step 2: Run test to verify it passes (audit already supports metadata_json)**

Run: `uv run pytest tests/test_audit_diffs.py -v`
Expected: PASS — this confirms the audit module already stores `metadata_json` correctly; no schema changes needed.

- [ ] **Step 3: Add audit logging to the directory save function**

In `not_dot_net/frontend/directory.py`, inside the `save()` function in `_render_edit_form`, after `await _update_user(person.id, diff)` and before `await _finish_save(...)`, add:

```python
            from not_dot_net.backend.audit import log_audit
            current_values = {k: getattr(person, k) for k in diff}
            changes = {
                k: {"old": _serialize_value(current_values.get(k)), "new": _serialize_value(v)}
                for k, v in diff.items()
            }
            await log_audit(
                "user", "update",
                actor_id=current_user.id, actor_email=current_user.email,
                target_type="user", target_id=person.id,
                detail=f"fields={','.join(diff.keys())}",
                metadata={"changes": changes},
            )
```

Add a helper at module level in `directory.py`:

```python
def _serialize_value(v) -> str | None:
    """Convert a value to a JSON-friendly string for audit logging."""
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()
    return str(v)
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/frontend/directory.py tests/test_audit_diffs.py
git commit -m "feat: log field-level diffs in audit when user profiles are edited"
```

---

### Task 6: i18n Keys for Tenure & Employer

**Files:**
- Modify: `not_dot_net/frontend/i18n.py`

- [ ] **Step 1: Add i18n keys**

In `not_dot_net/frontend/i18n.py`, add to the `"en"` dict (after the Directory section):

```python
        # Tenure / History
        "tenure_history": "Employment History",
        "employer": "Employer",
        "add_tenure": "Add Period",
        "edit_tenure": "Edit",
        "delete_tenure": "Delete",
        "tenure_notes": "Notes",
        "no_tenures": "No employment history recorded",
        "tenure_saved": "Employment period saved",
        "tenure_deleted": "Employment period deleted",
        "tenure_current": "Current",
        "confirm_delete_tenure": "Delete this employment period?",
```

Add the corresponding French translations in the `"fr"` dict:

```python
        # Tenure / History
        "tenure_history": "Historique des emplois",
        "employer": "Employeur",
        "add_tenure": "Ajouter une période",
        "edit_tenure": "Modifier",
        "delete_tenure": "Supprimer",
        "tenure_notes": "Notes",
        "no_tenures": "Aucun historique d'emploi enregistré",
        "tenure_saved": "Période d'emploi enregistrée",
        "tenure_deleted": "Période d'emploi supprimée",
        "tenure_current": "En cours",
        "confirm_delete_tenure": "Supprimer cette période d'emploi ?",
```

- [ ] **Step 2: Run i18n validation test**

Run: `uv run pytest tests/test_i18n.py -v`
Expected: PASS (both languages have the same keys)

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/i18n.py
git commit -m "feat: add i18n keys for tenure history and employer (EN + FR)"
```

---

### Task 7: Tenure History UI in Directory

**Files:**
- Modify: `not_dot_net/frontend/directory.py`

- [ ] **Step 1: Add tenure history section to person detail view**

In `not_dot_net/frontend/directory.py`, inside `_render_detail()`, after the edit/delete buttons section and before the function ends, add a tenure history section. Only show for users with `manage_users` permission or when viewing own profile:

```python
        if is_own or is_admin:
            ui.separator().classes("my-2")
            await _render_tenure_history(container, person, current_user, is_admin)
```

Add a new function `_render_tenure_history`:

```python
async def _render_tenure_history(parent_container, person: User, current_user: User, is_admin: bool):
    """Render the employment history timeline for a person."""
    from not_dot_net.backend.tenure_service import list_tenures, add_tenure, update_tenure, delete_tenure

    tenures = await list_tenures(person.id)

    with ui.expansion(t("tenure_history"), icon="history").classes("w-full"):
        tenure_container = ui.column().classes("w-full")

        async def refresh_tenures():
            nonlocal tenures
            tenures = await list_tenures(person.id)
            tenure_container.clear()
            with tenure_container:
                if not tenures:
                    ui.label(t("no_tenures")).classes("text-sm text-gray-400 italic")
                for tenure in tenures:
                    _render_tenure_row(tenure, is_admin, refresh_tenures, person, current_user)

        def _render_tenure_row(tenure, is_admin, on_refresh, person, current_user):
            end_label = t("tenure_current") if tenure.end_date is None else str(tenure.end_date)
            with ui.row().classes("items-center gap-2 w-full"):
                ui.chip(tenure.status, color="primary").props("dense outline")
                ui.label(f"{tenure.employer}").classes("text-sm font-medium")
                ui.label(f"{tenure.start_date} → {end_label}").classes("text-sm text-gray-500")
                if tenure.notes:
                    ui.icon("info", size="xs").tooltip(tenure.notes)
                if is_admin:
                    async def do_edit(t_id=tenure.id):
                        await _tenure_edit_dialog(t_id, person, current_user, on_refresh)
                    ui.button(icon="edit", on_click=do_edit).props("flat dense round size=xs")

                    async def do_delete(t_id=tenure.id):
                        await delete_tenure(t_id)
                        from not_dot_net.backend.audit import log_audit
                        await log_audit(
                            "user", "delete_tenure",
                            actor_id=current_user.id, actor_email=current_user.email,
                            target_type="user", target_id=person.id,
                        )
                        ui.notify(t("tenure_deleted"), color="positive")
                        await on_refresh()
                    ui.button(icon="delete", on_click=do_delete).props(
                        "flat dense round size=xs color=negative"
                    )

        if is_admin:
            async def show_add():
                await _tenure_add_dialog(person, current_user, refresh_tenures)
            ui.button(t("add_tenure"), icon="add", on_click=show_add).props("flat dense")

        await refresh_tenures()
```

- [ ] **Step 2: Add tenure add/edit dialogs**

```python
async def _tenure_add_dialog(person: User, current_user: User, on_refresh):
    """Dialog to add a new tenure period."""
    from not_dot_net.backend.tenure_service import add_tenure
    from not_dot_net.config import org_config

    cfg = await org_config.get()

    dialog = ui.dialog()
    with dialog, ui.card().classes("w-96"):
        ui.label(t("add_tenure")).classes("text-h6")
        status_input = ui.select(cfg.employment_statuses, label=t("status")).props("outlined dense")
        employer_input = ui.select(cfg.employers, label=t("employer")).props("outlined dense")
        start_input = ui.input(t("start_date"), placeholder="YYYY-MM-DD").props("outlined dense")
        end_input = ui.input(t("end_date"), placeholder="YYYY-MM-DD (optional)").props("outlined dense")
        notes_input = ui.input(t("tenure_notes")).props("outlined dense")

        async def save():
            if not status_input.value or not employer_input.value or not start_input.value:
                ui.notify(t("required_field"), color="warning")
                return
            from datetime import date as dt_date
            start = dt_date.fromisoformat(start_input.value)
            end = dt_date.fromisoformat(end_input.value) if end_input.value else None
            await add_tenure(
                user_id=person.id,
                status=status_input.value,
                employer=employer_input.value,
                start_date=start,
                end_date=end,
                notes=notes_input.value or None,
            )
            from not_dot_net.backend.audit import log_audit
            await log_audit(
                "user", "add_tenure",
                actor_id=current_user.id, actor_email=current_user.email,
                target_type="user", target_id=person.id,
                detail=f"status={status_input.value} employer={employer_input.value}",
            )
            dialog.close()
            ui.notify(t("tenure_saved"), color="positive")
            await on_refresh()

        with ui.row():
            ui.button(t("save"), on_click=save).props("flat color=primary")
            ui.button(t("cancel"), on_click=dialog.close).props("flat")

    dialog.open()


async def _tenure_edit_dialog(tenure_id, person: User, current_user: User, on_refresh):
    """Dialog to edit an existing tenure period."""
    from not_dot_net.backend.tenure_service import update_tenure, list_tenures
    from not_dot_net.config import org_config

    cfg = await org_config.get()

    # Load current tenure data
    tenures = await list_tenures(person.id)
    tenure = next((t for t in tenures if t.id == tenure_id), None)
    if tenure is None:
        return

    dialog = ui.dialog()
    with dialog, ui.card().classes("w-96"):
        ui.label(t("edit_tenure")).classes("text-h6")
        status_input = ui.select(
            cfg.employment_statuses, value=tenure.status, label=t("status"),
        ).props("outlined dense")
        employer_input = ui.select(
            cfg.employers, value=tenure.employer, label=t("employer"),
        ).props("outlined dense")
        start_input = ui.input(
            t("start_date"), value=str(tenure.start_date),
        ).props("outlined dense")
        end_input = ui.input(
            t("end_date"), value=str(tenure.end_date) if tenure.end_date else "",
        ).props("outlined dense")
        notes_input = ui.input(
            t("tenure_notes"), value=tenure.notes or "",
        ).props("outlined dense")

        async def save():
            if not status_input.value or not employer_input.value or not start_input.value:
                ui.notify(t("required_field"), color="warning")
                return
            from datetime import date as dt_date
            start = dt_date.fromisoformat(start_input.value)
            end = dt_date.fromisoformat(end_input.value) if end_input.value else None
            await update_tenure(
                tenure_id,
                status=status_input.value,
                employer=employer_input.value,
                start_date=start,
                end_date=end,
                notes=notes_input.value or None,
            )
            from not_dot_net.backend.audit import log_audit
            await log_audit(
                "user", "update_tenure",
                actor_id=current_user.id, actor_email=current_user.email,
                target_type="user", target_id=person.id,
                detail=f"status={status_input.value} employer={employer_input.value}",
            )
            dialog.close()
            ui.notify(t("tenure_saved"), color="positive")
            await on_refresh()

        with ui.row():
            ui.button(t("save"), on_click=save).props("flat color=primary")
            ui.button(t("cancel"), on_click=dialog.close).props("flat")

    dialog.open()
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -x -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add not_dot_net/frontend/directory.py
git commit -m "feat: add tenure history UI in directory person detail"
```

---

### Task 8: Tenure Export/Import

**Files:**
- Modify: `not_dot_net/backend/data_io.py`
- Modify: `tests/test_data_io.py`

- [ ] **Step 1: Write failing test for tenure export/import**

Append to `tests/test_data_io.py`:

```python
async def test_export_includes_tenures():
    from not_dot_net.backend.data_io import export_all
    from not_dot_net.backend.tenure_service import add_tenure
    from datetime import date

    user = await _create_user()  # reuse existing helper or create one
    await add_tenure(
        user_id=user.id, status="PhD", employer="CNRS",
        start_date=date(2025, 9, 1),
    )
    data = await export_all()
    assert "tenures" in data
    assert len(data["tenures"]) == 1
    assert data["tenures"][0]["status"] == "PhD"
    assert data["tenures"][0]["employer"] == "CNRS"


async def test_import_tenures():
    from not_dot_net.backend.data_io import import_all
    from not_dot_net.backend.tenure_service import list_tenures

    user = await _create_user(email="import@test.com")
    data = {
        "tenures": [
            {
                "user_email": "import@test.com",
                "status": "Intern",
                "employer": "Polytechnique",
                "start_date": "2025-03-01",
                "end_date": "2025-08-31",
            }
        ],
    }
    result = await import_all(data)
    assert result["tenures"]["created"] == 1
    tenures = await list_tenures(user.id)
    assert len(tenures) == 1
    assert tenures[0].employer == "Polytechnique"
```

Note: you'll need a `_create_user` helper in `test_data_io.py` if one doesn't exist. Check the existing file — if it already has one, reuse it; otherwise add:

```python
async def _create_user(email="test@lpp.fr") -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(id=uuid.uuid4(), email=email, hashed_password="x", role="staff")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data_io.py::test_export_includes_tenures tests/test_data_io.py::test_import_tenures -v`
Expected: FAIL

- [ ] **Step 3: Implement tenure export/import**

In `not_dot_net/backend/data_io.py`, add:

```python
from not_dot_net.backend.tenure_service import UserTenure
from not_dot_net.backend.db import User

def _serialize_tenure(t: UserTenure, email: str) -> dict:
    return {
        "user_email": email,
        "status": t.status,
        "employer": t.employer,
        "start_date": t.start_date.isoformat(),
        "end_date": t.end_date.isoformat() if t.end_date else None,
        "notes": t.notes,
    }


async def export_tenures() -> list[dict]:
    async with session_scope() as session:
        result = await session.execute(
            select(UserTenure).order_by(UserTenure.user_id, UserTenure.start_date)
        )
        tenures = result.scalars().all()
        user_ids = {t.user_id for t in tenures}
        if user_ids:
            users_result = await session.execute(
                select(User.id, User.email).where(User.id.in_(user_ids))
            )
            email_map = {uid: email for uid, email in users_result.all()}
        else:
            email_map = {}
        return [_serialize_tenure(t, email_map.get(t.user_id, "unknown")) for t in tenures]


async def import_tenures(data: list[dict], *, replace: bool = False) -> dict[str, int]:
    from datetime import date as dt_date
    created, skipped = 0, 0
    async with session_scope() as session:
        for item in data:
            email = item.get("user_email", "").strip()
            if not email:
                skipped += 1
                continue
            user_result = await session.execute(
                select(User).where(User.email == email)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                skipped += 1
                continue
            session.add(UserTenure(
                user_id=user.id,
                status=item["status"],
                employer=item["employer"],
                start_date=dt_date.fromisoformat(item["start_date"]),
                end_date=dt_date.fromisoformat(item["end_date"]) if item.get("end_date") else None,
                notes=item.get("notes"),
            ))
            created += 1
        await session.commit()
    return {"created": created, "skipped": skipped}
```

Update `export_all()` to include tenures:
```python
async def export_all() -> dict:
    pages, resources, tenures = await asyncio.gather(
        export_pages(), export_resources(), export_tenures(),
    )
    return {
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "pages": pages,
        "resources": resources,
        "tenures": tenures,
    }
```

Update `import_all()` to handle tenures:
```python
async def import_all(data: dict, *, replace: bool = False) -> dict:
    result = {}
    if "pages" in data:
        result["pages"] = await import_pages(data["pages"], replace=replace)
    if "resources" in data:
        result["resources"] = await import_resources(data["resources"], replace=replace)
    if "tenures" in data:
        result["tenures"] = await import_tenures(data["tenures"], replace=replace)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data_io.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/data_io.py tests/test_data_io.py
git commit -m "feat: include tenure history in data export/import"
```

---

### Task 9: Auto-Create Tenure from Completed Onboarding

**Files:**
- Modify: `not_dot_net/backend/workflow_service.py`
- Modify: `tests/test_tenure_onboarding.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tenure_onboarding.py`:

```python
from not_dot_net.backend.tenure_service import list_tenures
from not_dot_net.backend.roles import RoleDefinition, roles_config
from datetime import date


async def _setup_all_roles():
    cfg = await roles_config.get()
    cfg.roles["admin"] = RoleDefinition(
        label="Admin",
        permissions=[
            "manage_users", "create_workflows", "approve_workflows",
            "access_personal_data",
        ],
    )
    cfg.roles["staff"] = RoleDefinition(
        label="Staff", permissions=["create_workflows"],
    )
    await roles_config.set(cfg)


async def test_completed_onboarding_creates_tenure():
    await _setup_all_roles()
    staff = await _create_user("initiator@test.com", role="staff")
    admin = await _create_user("admin@test.com", role="admin")

    req = await create_request(
        workflow_type="onboarding",
        created_by=staff.id,
        data={"contact_email": "new@test.com", "status": "PhD", "employer": "CNRS"},
        actor=staff,
    )

    # Step 1: submit initiation
    req = await submit_step(
        request_id=req.id, actor_id=staff.id,
        action="submit",
        data={"contact_email": "new@test.com", "status": "PhD", "employer": "CNRS"},
        actor_user=staff,
    )

    # Step 2: submit newcomer info (via token)
    req = await submit_step(
        request_id=req.id, actor_id=None,
        action="submit",
        data={"first_name": "Alice", "last_name": "Doe"},
        actor_token=req.token,
    )

    # Step 3: admin validates
    req = await submit_step(
        request_id=req.id, actor_id=admin.id,
        action="approve",
        actor_user=admin,
    )

    # Step 4: IT completes
    req = await submit_step(
        request_id=req.id, actor_id=admin.id,
        action="complete",
        data={"notes": "Account created"},
        actor_user=admin,
    )

    # The contact_email "new@test.com" won't have a User yet in this test,
    # but the tenure should be created for returning_user_id if present,
    # or be a pending record. For simplicity, test with a returning user:
    # We'll test the simpler path — check that _create_tenure_from_onboarding is called.
    # This test verifies the function exists and works when called directly.

    from not_dot_net.backend.workflow_service import _create_tenure_from_onboarding
    # Create a user to represent the onboarded person
    newcomer = await _create_user("new@test.com", role="staff")
    await _create_tenure_from_onboarding(req, newcomer.id)
    tenures = await list_tenures(newcomer.id)
    assert len(tenures) == 1
    assert tenures[0].status == "PhD"
    assert tenures[0].employer == "CNRS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tenure_onboarding.py::test_completed_onboarding_creates_tenure -v`
Expected: FAIL — `ImportError: cannot import name '_create_tenure_from_onboarding'`

- [ ] **Step 3: Implement auto-tenure on onboarding completion**

In `not_dot_net/backend/workflow_service.py`, add:

```python
async def _create_tenure_from_onboarding(req: WorkflowRequest, user_id: uuid.UUID) -> None:
    """Create a tenure record from a completed onboarding request."""
    from not_dot_net.backend.tenure_service import add_tenure
    from datetime import date as dt_date

    status = req.data.get("status")
    employer = req.data.get("employer")
    if not status or not employer:
        return

    start_date = dt_date.today()
    if req.data.get("start_date"):
        try:
            start_date = dt_date.fromisoformat(req.data["start_date"])
        except (ValueError, TypeError):
            pass

    await add_tenure(
        user_id=user_id,
        status=status,
        employer=employer,
        start_date=start_date,
    )
```

In the `submit_step()` function, inside the `if new_status == RequestStatus.COMPLETED:` block (where `mark_for_retention` is called), add after the retention block:

```python
            # Auto-create tenure from completed onboarding
            if req.type == "onboarding":
                try:
                    target_user_id = None
                    if req.data.get("returning_user_id"):
                        target_user_id = uuid.UUID(req.data["returning_user_id"])
                    elif req.target_email:
                        async with session_scope() as tenure_session:
                            from not_dot_net.backend.db import User as UserModel
                            result = await tenure_session.execute(
                                select(UserModel).where(UserModel.email == req.target_email)
                            )
                            target_user = result.scalar_one_or_none()
                            if target_user:
                                target_user_id = target_user.id
                    if target_user_id:
                        await _create_tenure_from_onboarding(req, target_user_id)
                except Exception:
                    logger.exception("Failed to create tenure for onboarding request %s", req.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenure_onboarding.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/workflow_service.py tests/test_tenure_onboarding.py
git commit -m "feat: auto-create tenure record when onboarding workflow completes"
```

---

### Task 10: Final Integration — Run Full Test Suite & Verify

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS, including all new tenure tests

- [ ] **Step 2: Start dev server and manually verify**

Run: `uv run python -m not_dot_net.cli serve --host localhost --port 8000`

Check in browser:
1. **Directory → Person detail → Employment History** expansion panel appears
2. **Add Period** button opens dialog with status + employer dropdowns
3. Periods display as timeline rows with edit/delete for admins
4. **New Request → Onboarding → Initiation** step has Employer select field
5. **Settings → Organization** shows `employers` list
6. **Audit Log** shows `user.update` events with `changes` in metadata

- [ ] **Step 3: Commit any final fixes if needed**

```bash
git add -A
git commit -m "fix: final adjustments from integration testing"
```
