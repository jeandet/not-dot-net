# Workflow Engine Implementation Plan (Part 1: Roles + Engine + Data Model)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement user roles, YAML-driven workflow config, workflow DB models, pure step machine engine, and workflow service layer — the complete backend for multi-step workflows.

**Architecture:** Roles are an ordered enum on the User model. Workflow definitions live in YAML config validated by Pydantic. The step machine is a pure-function engine (`workflow_engine.py`) that computes transitions and validity. The service layer (`workflow_service.py`) calls the engine then persists to DB. Old onboarding code is replaced.

**Tech Stack:** SQLAlchemy async + aiosqlite, Pydantic models for config validation, pytest for testing.

**Spec:** `docs/superpowers/specs/2026-03-22-workflow-engine-design.md`

---

### Task 1: User Roles

**Files:**
- Create: `not_dot_net/backend/roles.py`
- Modify: `not_dot_net/backend/db.py`
- Modify: `not_dot_net/backend/schemas.py`
- Modify: `not_dot_net/backend/users.py`
- Modify: `tests/test_model.py`
- Create: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests for Role enum and has_role**

```python
# tests/test_roles.py
from not_dot_net.backend.roles import Role, has_role


def test_role_ordering():
    assert Role.MEMBER < Role.STAFF < Role.DIRECTOR < Role.ADMIN


def test_has_role_exact_match():
    class FakeUser:
        role = Role.STAFF
    assert has_role(FakeUser(), Role.STAFF)


def test_has_role_higher_passes():
    class FakeUser:
        role = Role.DIRECTOR
    assert has_role(FakeUser(), Role.STAFF)


def test_has_role_lower_fails():
    class FakeUser:
        role = Role.MEMBER
    assert not has_role(FakeUser(), Role.STAFF)


def test_role_values_are_strings():
    assert Role.MEMBER.value == "member"
    assert Role.STAFF.value == "staff"
    assert Role.DIRECTOR.value == "director"
    assert Role.ADMIN.value == "admin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_roles.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement roles.py**

```python
# not_dot_net/backend/roles.py
from enum import Enum as PyEnum


class Role(str, PyEnum):
    MEMBER = "member"
    STAFF = "staff"
    DIRECTOR = "director"
    ADMIN = "admin"


_ROLE_ORDER = {Role.MEMBER: 0, Role.STAFF: 1, Role.DIRECTOR: 2, Role.ADMIN: 3}


def has_role(user, minimum_role: Role) -> bool:
    """Check if user has at least the given role level."""
    user_role = user.role if isinstance(user.role, Role) else Role(user.role)
    return _ROLE_ORDER[user_role] >= _ROLE_ORDER[minimum_role]
```

- [ ] **Step 4: Update test to match string enum approach**

```python
# tests/test_roles.py
from not_dot_net.backend.roles import Role, has_role


def test_role_values_are_strings():
    assert Role.MEMBER.value == "member"
    assert Role.STAFF.value == "staff"
    assert Role.DIRECTOR.value == "director"
    assert Role.ADMIN.value == "admin"


def test_has_role_exact_match():
    class FakeUser:
        role = Role.STAFF
    assert has_role(FakeUser(), Role.STAFF)


def test_has_role_higher_passes():
    class FakeUser:
        role = Role.DIRECTOR
    assert has_role(FakeUser(), Role.STAFF)


def test_has_role_lower_fails():
    class FakeUser:
        role = Role.MEMBER
    assert not has_role(FakeUser(), Role.STAFF)


def test_has_role_with_string_value():
    class FakeUser:
        role = "director"
    assert has_role(FakeUser(), Role.STAFF)
    assert has_role(FakeUser(), Role.DIRECTOR)
    assert not has_role(FakeUser(), Role.ADMIN)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_roles.py -v`
Expected: PASS

- [ ] **Step 6: Add role column to User model**

Modify `not_dot_net/backend/db.py`:
- Import `Role` from `not_dot_net.backend.roles`
- Add to User class:
```python
role: Mapped[Role] = mapped_column(
    SAEnum(Role), default=Role.MEMBER
)
```

- [ ] **Step 7: Add role to schemas**

Modify `not_dot_net/backend/schemas.py`:
- Import `Role` from `not_dot_net.backend.roles`
- Add to `UserRead`: `role: Role = Role.MEMBER`
- Add to `UserUpdate`: `role: Role | None = None`

- [ ] **Step 8: Update test_model.py**

Add `"role"` to the `PROFILE_FIELDS` list. Add a test:
```python
def test_user_default_role():
    from not_dot_net.backend.roles import Role
    user = User(email="test@example.com", hashed_password="x")
    assert user.role == Role.MEMBER
```

- [ ] **Step 9: Update seed users with roles**

Modify `not_dot_net/backend/users.py`:
- Import `Role` from `not_dot_net.backend.roles`
- Add `"role"` key to each entry in `FAKE_USERS`:
  - Marie Curie: `"staff"`, Pierre Dumont: `"staff"`, Sophie Martin: `"staff"`
  - Nicolas Lambert: `"director"` (professor — lab director stand-in)
  - Camille Moreau: `"staff"`, Jean Dupont: `"staff"`
  - Lucas Bernard, Emma Petit: `"member"` (PhD students)
  - Thomas Leroy: `"member"` (intern), Alice Roux: `"member"` (visitor)
- In `seed_fake_users()`, add `"role"` to the `for field in (...)` loop

Replace the entire `ensure_default_admin()` function body:

```python
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
                    print(f"Default admin '{settings.admin_email}' created.")
                except UserAlreadyExists:
                    pass
```

- [ ] **Step 10: Implement is_superuser sync**

Per spec: "The existing `is_superuser` field is kept in sync: set to `True` when role is `admin`, `False` otherwise."

Add an `on_after_update` hook to `UserManager` in `users.py`:

```python
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    # ... existing methods ...

    async def on_after_update(self, user: User, update_dict: dict, request=None):
        if "role" in update_dict:
            from not_dot_net.backend.roles import Role
            user.is_superuser = (user.role == Role.ADMIN)
```

This ensures any role change via FastAPI-Users routes automatically syncs `is_superuser`.

- [ ] **Step 11: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 12: Commit**

```bash
git add not_dot_net/backend/roles.py not_dot_net/backend/db.py not_dot_net/backend/schemas.py not_dot_net/backend/users.py tests/test_roles.py tests/test_model.py
git commit -m "feat: add user roles (member/staff/director/admin) with ordered permissions"
```

---

### Task 2: Workflow Config Pydantic Models

**Files:**
- Modify: `not_dot_net/config.py`
- Create: `tests/test_workflow_config.py`

- [ ] **Step 1: Write failing tests for workflow config validation**

```python
# tests/test_workflow_config.py
import pytest
from not_dot_net.config import Settings, WorkflowStepConfig, WorkflowConfig


def _make_settings(**kwargs):
    defaults = dict(jwt_secret="x" * 34, storage_secret="x" * 34)
    defaults.update(kwargs)
    return Settings(**defaults)


def test_settings_has_workflows():
    s = _make_settings()
    assert hasattr(s, "workflows")
    assert isinstance(s.workflows, dict)


def test_default_workflows_include_onboarding_and_vpn():
    s = _make_settings()
    assert "onboarding" in s.workflows
    assert "vpn_access" in s.workflows


def test_workflow_config_has_required_fields():
    s = _make_settings()
    wf = s.workflows["vpn_access"]
    assert wf.label == "VPN Access Request"
    assert wf.start_role == "staff"
    assert wf.target_email_field == "target_email"
    assert len(wf.steps) >= 2


def test_step_config_fields():
    s = _make_settings()
    step = s.workflows["vpn_access"].steps[0]
    assert step.key == "request"
    assert step.type == "form"
    assert step.assignee_role == "staff"
    assert len(step.fields) >= 2
    assert "submit" in step.actions


def test_step_field_config():
    s = _make_settings()
    field = s.workflows["vpn_access"].steps[0].fields[0]
    assert field.name == "target_name"
    assert field.type == "text"
    assert field.required is True


def test_notification_config():
    s = _make_settings()
    notifs = s.workflows["vpn_access"].notifications
    assert len(notifs) >= 1
    assert notifs[0].event == "submit"
    assert "director" in notifs[0].notify


def test_settings_has_mail_config():
    s = _make_settings()
    assert hasattr(s, "mail")
    assert s.mail.dev_mode is True  # default for dev


def test_onboarding_has_partial_save_step():
    s = _make_settings()
    newcomer_step = s.workflows["onboarding"].steps[1]
    assert newcomer_step.key == "newcomer_info"
    assert newcomer_step.partial_save is True
    assert newcomer_step.assignee == "target_person"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_config.py -v`
Expected: FAIL (imports don't exist yet)

- [ ] **Step 3: Implement config models**

Add to `not_dot_net/config.py` (before Settings class):

```python
class FieldConfig(BaseModel):
    name: str
    type: str  # text, email, textarea, date, select, file
    required: bool = False
    label: str = ""
    options_key: str | None = None  # for select: key in Settings (e.g. "teams")


class NotificationRuleConfig(BaseModel):
    event: str  # submit, approve, reject
    step: str | None = None  # None = match any step
    notify: list[str]  # role names or contextual: requester, target_person


class WorkflowStepConfig(BaseModel):
    key: str
    type: str  # form, approval
    assignee_role: str | None = None
    assignee: str | None = None  # contextual: target_person, requester
    fields: list[FieldConfig] = []
    actions: list[str] = []
    partial_save: bool = False


class WorkflowConfig(BaseModel):
    label: str
    start_role: str = "staff"
    target_email_field: str | None = None
    steps: list[WorkflowStepConfig]
    notifications: list[NotificationRuleConfig] = []


class MailSettings(BaseModel):
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_tls: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = "noreply@not-dot-net.dev"
    dev_mode: bool = True
    dev_catch_all: str = ""
```

Add to `Settings` class:
```python
mail: MailSettings = MailSettings()
workflows: dict[str, WorkflowConfig] = {
    "vpn_access": WorkflowConfig(
        label="VPN Access Request",
        start_role="staff",
        target_email_field="target_email",
        steps=[
            WorkflowStepConfig(
                key="request",
                type="form",
                assignee_role="staff",
                fields=[
                    FieldConfig(name="target_name", type="text", required=True, label="Person Name"),
                    FieldConfig(name="target_email", type="email", required=True, label="Person Email"),
                    FieldConfig(name="justification", type="textarea", required=False, label="Justification"),
                ],
                actions=["submit"],
            ),
            WorkflowStepConfig(
                key="approval",
                type="approval",
                assignee_role="director",
                actions=["approve", "reject"],
            ),
        ],
        notifications=[
            NotificationRuleConfig(event="submit", step="request", notify=["director"]),
            NotificationRuleConfig(event="approve", notify=["requester", "target_person"]),
            NotificationRuleConfig(event="reject", notify=["requester"]),
        ],
    ),
    "onboarding": WorkflowConfig(
        label="Onboarding",
        start_role="staff",
        target_email_field="person_email",
        steps=[
            WorkflowStepConfig(
                key="request",
                type="form",
                assignee_role="staff",
                fields=[
                    FieldConfig(name="person_name", type="text", required=True),
                    FieldConfig(name="person_email", type="email", required=True),
                    FieldConfig(name="role_status", type="select", options_key="roles", required=True),
                    FieldConfig(name="team", type="select", options_key="teams", required=True),
                    FieldConfig(name="start_date", type="date", required=True),
                    FieldConfig(name="note", type="textarea", required=False),
                ],
                actions=["submit"],
            ),
            WorkflowStepConfig(
                key="newcomer_info",
                type="form",
                assignee="target_person",
                partial_save=True,
                fields=[
                    FieldConfig(name="id_document", type="file", required=True, label="ID Copy"),
                    FieldConfig(name="rib", type="file", required=True, label="Bank Details (RIB)"),
                    FieldConfig(name="photo", type="file", required=False, label="Badge Photo"),
                    FieldConfig(name="phone", type="text", required=True),
                    FieldConfig(name="emergency_contact", type="text", required=True),
                ],
                actions=["submit"],
            ),
            WorkflowStepConfig(
                key="admin_validation",
                type="approval",
                assignee_role="admin",
                actions=["approve", "reject"],
            ),
        ],
        notifications=[
            NotificationRuleConfig(event="submit", step="request", notify=["target_person"]),
            NotificationRuleConfig(event="submit", step="newcomer_info", notify=["admin"]),
            NotificationRuleConfig(event="approve", notify=["requester", "target_person"]),
            NotificationRuleConfig(event="reject", notify=["requester"]),
        ],
    ),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_config.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/config.py tests/test_workflow_config.py
git commit -m "feat: add workflow and mail config models with default onboarding and VPN workflows"
```

---

### Task 3: Workflow Database Models

**Files:**
- Create: `not_dot_net/backend/workflow_models.py`
- Modify: `not_dot_net/backend/db.py` (import new models instead of onboarding)
- Create: `tests/test_workflow_models.py`

- [ ] **Step 1: Write failing tests for workflow models**

```python
# tests/test_workflow_models.py
from not_dot_net.backend.workflow_models import WorkflowRequest, WorkflowEvent, WorkflowFile


WORKFLOW_REQUEST_FIELDS = [
    "id", "type", "current_step", "status", "data", "created_by",
    "target_email", "token", "token_expires_at", "created_at", "updated_at",
]

WORKFLOW_EVENT_FIELDS = [
    "id", "request_id", "step_key", "action", "actor_id",
    "actor_token", "data_snapshot", "comment", "created_at",
]

WORKFLOW_FILE_FIELDS = [
    "id", "request_id", "step_key", "field_name", "filename",
    "storage_path", "uploaded_by", "uploaded_at",
]


def test_workflow_request_has_all_fields():
    for field in WORKFLOW_REQUEST_FIELDS:
        assert hasattr(WorkflowRequest, field), f"Missing field: {field}"


def test_workflow_event_has_all_fields():
    for field in WORKFLOW_EVENT_FIELDS:
        assert hasattr(WorkflowEvent, field), f"Missing field: {field}"


def test_workflow_file_has_all_fields():
    for field in WORKFLOW_FILE_FIELDS:
        assert hasattr(WorkflowFile, field), f"Missing field: {field}"


def test_workflow_request_defaults():
    req = WorkflowRequest(type="test", current_step="step1")
    assert req.status == "in_progress"
    assert req.data == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_models.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement workflow_models.py**

```python
# not_dot_net/backend/workflow_models.py
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from not_dot_net.backend.db import Base


class WorkflowRequest(Base):
    __tablename__ = "workflow_request"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(100))
    current_step: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="in_progress")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    target_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class WorkflowEvent(Base):
    __tablename__ = "workflow_event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_request.id", ondelete="CASCADE")
    )
    step_key: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    actor_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WorkflowFile(Base):
    __tablename__ = "workflow_file"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_request.id", ondelete="CASCADE")
    )
    step_key: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

- [ ] **Step 4: Update db.py to import workflow_models instead of onboarding**

In `not_dot_net/backend/db.py`, change line 50:
```python
# Old:
import not_dot_net.backend.onboarding  # noqa: F401 — register model with Base
# New:
import not_dot_net.backend.workflow_models  # noqa: F401 — register models with Base
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_models.py -v`
Expected: PASS

- [ ] **Step 6: Update test_model.py to remove onboarding model tests**

Remove the `ONBOARDING_FIELDS` list and `test_onboarding_request_has_field` test from `tests/test_model.py` since the model no longer exists.

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -x -v`
Expected: Some tests in `test_onboarding_api.py` and `test_onboarding_ui.py` will fail because they reference `OnboardingRequest` and the old onboarding router. These tests need to be removed/replaced.

- [ ] **Step 8: Remove old onboarding tests and code**

- Delete `tests/test_onboarding_api.py`
- Delete `tests/test_onboarding_ui.py`
- Delete `not_dot_net/backend/onboarding.py`
- Delete `not_dot_net/backend/onboarding_router.py`
- Delete `not_dot_net/frontend/onboarding.py`
- In `not_dot_net/app.py`: remove the import and `app.include_router(onboarding_router)` line
- In `not_dot_net/frontend/shell.py`: remove the import of `render_onboarding` and the Onboarding tab panel (temporarily — dashboard replaces it in Plan 3). Keep just the People tab for now.

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 10: Commit**

```bash
git add not_dot_net/backend/workflow_models.py not_dot_net/backend/db.py tests/test_workflow_models.py tests/test_model.py
git rm not_dot_net/backend/onboarding.py not_dot_net/backend/onboarding_router.py not_dot_net/frontend/onboarding.py tests/test_onboarding_api.py tests/test_onboarding_ui.py
git add not_dot_net/app.py not_dot_net/frontend/shell.py
git commit -m "feat: add workflow DB models, remove old onboarding code"
```

---

### Task 4: Workflow Step Machine (Pure Engine)

**Files:**
- Create: `not_dot_net/backend/workflow_engine.py`
- Create: `tests/test_workflow_engine.py`

- [ ] **Step 1: Write failing tests for the step machine**

```python
# tests/test_workflow_engine.py
import pytest
from not_dot_net.backend.workflow_engine import (
    get_current_step_config,
    get_available_actions,
    compute_next_step,
    can_user_act,
    get_completion_status,
)
from not_dot_net.backend.roles import Role
from not_dot_net.config import WorkflowConfig, WorkflowStepConfig, FieldConfig


# --- Fixtures: minimal workflow configs ---

TWO_STEP_WORKFLOW = WorkflowConfig(
    label="Test",
    start_role="staff",
    steps=[
        WorkflowStepConfig(key="form1", type="form", assignee_role="staff", actions=["submit"]),
        WorkflowStepConfig(key="approve", type="approval", assignee_role="director", actions=["approve", "reject"]),
    ],
)

PARTIAL_SAVE_WORKFLOW = WorkflowConfig(
    label="Test Partial",
    start_role="staff",
    steps=[
        WorkflowStepConfig(
            key="info",
            type="form",
            assignee="target_person",
            partial_save=True,
            fields=[
                FieldConfig(name="phone", type="text", required=True),
                FieldConfig(name="doc", type="file", required=True),
                FieldConfig(name="note", type="textarea", required=False),
            ],
            actions=["submit"],
        ),
    ],
)


class FakeRequest:
    def __init__(self, current_step, status="in_progress", data=None, target_email=None, created_by=None):
        self.current_step = current_step
        self.status = status
        self.data = data or {}
        self.target_email = target_email
        self.created_by = created_by


class FakeUser:
    def __init__(self, role, email="user@test.com", id="user-1"):
        self.role = role if isinstance(role, Role) else Role(role)
        self.email = email
        self.id = id


# --- Tests ---

def test_get_current_step_config():
    req = FakeRequest(current_step="approve")
    step = get_current_step_config(req, TWO_STEP_WORKFLOW)
    assert step.key == "approve"
    assert step.type == "approval"


def test_get_current_step_config_invalid():
    req = FakeRequest(current_step="nonexistent")
    assert get_current_step_config(req, TWO_STEP_WORKFLOW) is None


def test_get_available_actions_form():
    req = FakeRequest(current_step="form1")
    actions = get_available_actions(req, TWO_STEP_WORKFLOW)
    assert actions == ["submit"]


def test_get_available_actions_approval():
    req = FakeRequest(current_step="approve")
    actions = get_available_actions(req, TWO_STEP_WORKFLOW)
    assert set(actions) == {"approve", "reject"}


def test_get_available_actions_completed_request():
    req = FakeRequest(current_step="approve", status="completed")
    actions = get_available_actions(req, TWO_STEP_WORKFLOW)
    assert actions == []


def test_compute_next_step_submit_advances():
    result = compute_next_step(TWO_STEP_WORKFLOW, "form1", "submit")
    assert result == ("approve", "in_progress")


def test_compute_next_step_approve_last_completes():
    result = compute_next_step(TWO_STEP_WORKFLOW, "approve", "approve")
    assert result == (None, "completed")


def test_compute_next_step_reject_terminates():
    result = compute_next_step(TWO_STEP_WORKFLOW, "approve", "reject")
    assert result == (None, "rejected")


def test_can_user_act_role_match():
    user = FakeUser(Role.STAFF)
    req = FakeRequest(current_step="form1")
    assert can_user_act(user, req, TWO_STEP_WORKFLOW)


def test_can_user_act_role_higher():
    user = FakeUser(Role.DIRECTOR)
    req = FakeRequest(current_step="form1")
    assert can_user_act(user, req, TWO_STEP_WORKFLOW)


def test_can_user_act_role_too_low():
    user = FakeUser(Role.MEMBER)
    req = FakeRequest(current_step="form1")
    assert not can_user_act(user, req, TWO_STEP_WORKFLOW)


def test_can_user_act_target_person():
    user = FakeUser(Role.MEMBER, email="target@test.com")
    req = FakeRequest(current_step="info", target_email="target@test.com")
    assert can_user_act(user, req, PARTIAL_SAVE_WORKFLOW)


def test_can_user_act_wrong_target():
    user = FakeUser(Role.MEMBER, email="other@test.com")
    req = FakeRequest(current_step="info", target_email="target@test.com")
    assert not can_user_act(user, req, PARTIAL_SAVE_WORKFLOW)


def test_get_available_actions_partial_save_includes_save_draft():
    req = FakeRequest(current_step="info")
    actions = get_available_actions(req, PARTIAL_SAVE_WORKFLOW)
    assert "save_draft" in actions
    assert "submit" in actions


def test_completion_status_all_missing():
    req = FakeRequest(current_step="info", data={})
    step = PARTIAL_SAVE_WORKFLOW.steps[0]
    status = get_completion_status(req, step, files={})
    assert status["phone"] is False
    assert status["doc"] is False
    assert "note" not in status  # optional fields not tracked


def test_completion_status_partial():
    req = FakeRequest(current_step="info", data={"phone": "+33 1 23"})
    step = PARTIAL_SAVE_WORKFLOW.steps[0]
    status = get_completion_status(req, step, files={})
    assert status["phone"] is True
    assert status["doc"] is False


def test_completion_status_complete():
    req = FakeRequest(current_step="info", data={"phone": "+33 1 23"})
    step = PARTIAL_SAVE_WORKFLOW.steps[0]
    status = get_completion_status(req, step, files={"doc": True})
    assert status["phone"] is True
    assert status["doc"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_engine.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement workflow_engine.py**

```python
# not_dot_net/backend/workflow_engine.py
"""Pure-function workflow step machine. No DB, no side effects."""

from not_dot_net.backend.roles import Role, has_role
from not_dot_net.config import WorkflowConfig, WorkflowStepConfig


def get_current_step_config(request, workflow: WorkflowConfig) -> WorkflowStepConfig | None:
    """Get the step config for the request's current step."""
    for step in workflow.steps:
        if step.key == request.current_step:
            return step
    return None


def get_available_actions(request, workflow: WorkflowConfig) -> list[str]:
    """Get actions available for the current step. Empty if request is terminal."""
    if request.status in ("completed", "rejected", "cancelled"):
        return []
    step = get_current_step_config(request, workflow)
    if step is None:
        return []
    actions = list(step.actions)
    if step.partial_save and "save_draft" not in actions:
        actions.append("save_draft")
    return actions


def compute_next_step(
    workflow: WorkflowConfig, current_step_key: str, action: str
) -> tuple[str | None, str]:
    """Given an action, return (next_step_key, new_status).

    Returns (None, "completed") if last step approved.
    Returns (None, "rejected") if rejected.
    """
    if action == "reject":
        return (None, "rejected")

    if action == "save_draft":
        return (current_step_key, "in_progress")

    # submit or approve → advance to next step
    step_keys = [s.key for s in workflow.steps]
    idx = step_keys.index(current_step_key)
    if idx + 1 < len(step_keys):
        return (step_keys[idx + 1], "in_progress")
    return (None, "completed")


def can_user_act(user, request, workflow: WorkflowConfig) -> bool:
    """Check if a user can act on the current step."""
    step = get_current_step_config(request, workflow)
    if step is None:
        return False

    # Role-based assignment
    if step.assignee_role:
        return has_role(user, Role(step.assignee_role))

    # Contextual assignment
    if step.assignee == "target_person":
        return user.email == request.target_email
    if step.assignee == "requester":
        return str(user.id) == str(request.created_by)

    # NOTE: `assignee: step:<key>:actor` is deferred to Plan 2/3 when event
    # history queries are wired up. Not needed for onboarding or VPN workflows.

    return False


def get_completion_status(
    request, step: WorkflowStepConfig, files: dict[str, bool]
) -> dict[str, bool]:
    """For a form step, return {field_name: is_filled} for required fields only."""
    status = {}
    for field in step.fields:
        if not field.required:
            continue
        if field.type == "file":
            status[field.name] = files.get(field.name, False)
        else:
            value = request.data.get(field.name)
            status[field.name] = bool(value)
    return status
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_engine.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/workflow_engine.py tests/test_workflow_engine.py
git commit -m "feat: implement pure-function workflow step machine"
```

---

### Task 5: Workflow Service Layer

**Files:**
- Create: `not_dot_net/backend/workflow_service.py`
- Create: `tests/test_workflow_service.py`

This task requires an async test setup with a real in-memory SQLite DB, following the pattern from the existing `test_onboarding_api.py` (which we deleted). We recreate this pattern for workflow tests.

- [ ] **Step 0: Add pytest-asyncio configuration**

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:
```toml
asyncio_mode = "auto"
```

And ensure `pytest-asyncio` is a dev dependency:
```bash
uv pip install pytest-asyncio
```

- [ ] **Step 1: Write failing tests for workflow service**

```python
# tests/test_workflow_service.py
import pytest
import uuid
from not_dot_net.backend.workflow_service import (
    create_request,
    submit_step,
    save_draft,
    list_user_requests,
    list_actionable,
    get_request_by_id,
)
from not_dot_net.backend.roles import Role
from not_dot_net.backend.db import Base, User, init_db, get_async_session
from not_dot_net.config import init_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from contextlib import asynccontextmanager
import not_dot_net.backend.db as db_module
import not_dot_net.backend.workflow_models  # noqa: F401


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up an in-memory SQLite DB for each test."""
    init_settings()  # defaults
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session


async def _create_user(email="staff@test.com", role=Role.STAFF) -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password="x",
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_create_request():
    user = await _create_user()
    req = await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    assert req.type == "vpn_access"
    assert req.current_step == "request"
    assert req.status == "in_progress"
    assert req.target_email == "alice@test.com"
    assert req.data["target_name"] == "Alice"


async def test_submit_step_advances():
    user = await _create_user()
    req = await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    updated = await submit_step(req.id, user.id, "submit", data={})
    assert updated.current_step == "approval"
    assert updated.status == "in_progress"


async def test_approve_completes_workflow():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    req = await submit_step(req.id, staff.id, "submit", data={})
    req = await submit_step(req.id, director.id, "approve", data={})
    assert req.status == "completed"


async def test_reject_terminates_workflow():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )
    req = await submit_step(req.id, staff.id, "submit", data={})
    req = await submit_step(req.id, director.id, "reject", data={}, comment="Not justified")
    assert req.status == "rejected"


async def test_save_draft():
    user = await _create_user()
    req = await create_request(
        workflow_type="onboarding",
        created_by=user.id,
        data={"person_name": "Bob", "person_email": "bob@test.com",
              "role_status": "intern", "team": "Plasma Physics",
              "start_date": "2026-04-01"},
    )
    # Advance to newcomer_info step
    req = await submit_step(req.id, user.id, "submit", data={})
    assert req.current_step == "newcomer_info"
    # Save partial data
    req = await save_draft(req.id, data={"phone": "+33 1 23 45"})
    assert req.data["phone"] == "+33 1 23 45"
    assert req.current_step == "newcomer_info"  # still same step


async def test_list_user_requests():
    user = await _create_user()
    await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "A", "target_email": "a@test.com"},
    )
    await create_request(
        workflow_type="vpn_access",
        created_by=user.id,
        data={"target_name": "B", "target_email": "b@test.com"},
    )
    requests = await list_user_requests(user.id)
    assert len(requests) == 2


async def test_list_actionable_by_role():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)
    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "A", "target_email": "a@test.com"},
    )
    # Submit first step to move to approval
    await submit_step(req.id, staff.id, "submit", data={})
    # Director should see it as actionable
    actionable = await list_actionable(director)
    assert len(actionable) == 1
    assert actionable[0].current_step == "approval"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement workflow_service.py**

```python
# not_dot_net/backend/workflow_service.py
"""Workflow service layer — DB operations that use the step machine engine."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from not_dot_net.backend.db import get_async_session
from not_dot_net.backend.roles import Role, has_role
from not_dot_net.backend.workflow_engine import (
    compute_next_step,
    get_current_step_config,
)
from not_dot_net.backend.workflow_models import WorkflowEvent, WorkflowRequest
from not_dot_net.config import get_settings


def _get_workflow_config(workflow_type: str):
    settings = get_settings()
    wf = settings.workflows.get(workflow_type)
    if wf is None:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
    return wf


async def create_request(
    workflow_type: str,
    created_by: uuid.UUID,
    data: dict,
) -> WorkflowRequest:
    wf = _get_workflow_config(workflow_type)
    first_step = wf.steps[0].key

    # Resolve target_email from data if configured
    target_email = None
    if wf.target_email_field:
        target_email = data.get(wf.target_email_field)

    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        req = WorkflowRequest(
            type=workflow_type,
            current_step=first_step,
            status="in_progress",
            data=data,
            created_by=created_by,
            target_email=target_email,
        )
        session.add(req)

        event = WorkflowEvent(
            request_id=req.id,
            step_key=first_step,
            action="create",
            actor_id=created_by,
            data_snapshot=data,
        )
        session.add(event)
        await session.commit()
        await session.refresh(req)
        return req


async def submit_step(
    request_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    data: dict | None = None,
    comment: str | None = None,
    actor_user=None,
) -> WorkflowRequest:
    """Submit an action on the current step. Pass actor_user for authorization check."""
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        req = await session.get(WorkflowRequest, request_id)
        if req is None:
            raise ValueError(f"Request {request_id} not found")

        wf = _get_workflow_config(req.type)

        # Authorization: verify actor can act on this step
        if actor_user is not None:
            from not_dot_net.backend.workflow_engine import can_user_act
            if not can_user_act(actor_user, req, wf):
                raise PermissionError("User cannot act on this step")

        next_step, new_status = compute_next_step(wf, req.current_step, action)

        # Merge new data
        if data:
            merged = dict(req.data)
            merged.update(data)
            req.data = merged

        # Log event
        event = WorkflowEvent(
            request_id=req.id,
            step_key=req.current_step,
            action=action,
            actor_id=actor_id,
            data_snapshot=data,
            comment=comment,
        )
        session.add(event)

        # Transition
        if next_step:
            req.current_step = next_step
        req.status = new_status

        # Clear token on step completion
        if action != "save_draft":
            req.token = None
            req.token_expires_at = None

        # Generate token if next step is for target_person
        if next_step and new_status == "in_progress":
            next_step_config = None
            for s in wf.steps:
                if s.key == next_step:
                    next_step_config = s
                    break
            if next_step_config and next_step_config.assignee == "target_person":
                req.token = str(uuid.uuid4())
                req.token_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        await session.commit()
        await session.refresh(req)
        return req


async def save_draft(
    request_id: uuid.UUID,
    data: dict,
    actor_id: uuid.UUID | None = None,
    actor_token: str | None = None,
    actor_user=None,
) -> WorkflowRequest:
    """Save partial data on a form step with partial_save enabled."""
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        req = await session.get(WorkflowRequest, request_id)
        if req is None:
            raise ValueError(f"Request {request_id} not found")

        wf = _get_workflow_config(req.type)

        # Authorization: verify actor can act on this step
        if actor_user is not None:
            from not_dot_net.backend.workflow_engine import can_user_act
            if not can_user_act(actor_user, req, wf):
                raise PermissionError("User cannot act on this step")

        merged = dict(req.data)
        merged.update(data)
        req.data = merged

        event = WorkflowEvent(
            request_id=req.id,
            step_key=req.current_step,
            action="save_draft",
            actor_id=actor_id,
            actor_token=actor_token,
            data_snapshot=data,
        )
        session.add(event)
        await session.commit()
        await session.refresh(req)
        return req


async def get_request_by_id(request_id: uuid.UUID) -> WorkflowRequest | None:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        return await session.get(WorkflowRequest, request_id)


async def get_request_by_token(token: str) -> WorkflowRequest | None:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRequest).where(
                WorkflowRequest.token == token,
                WorkflowRequest.status == "in_progress",
                WorkflowRequest.token_expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()


async def list_user_requests(user_id: uuid.UUID) -> list[WorkflowRequest]:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRequest)
            .where(WorkflowRequest.created_by == user_id)
            .order_by(WorkflowRequest.created_at.desc())
        )
        return list(result.scalars().all())


async def list_actionable(user) -> list[WorkflowRequest]:
    """List requests where this user can act on the current step."""
    settings = get_settings()
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRequest)
            .where(WorkflowRequest.status == "in_progress")
            .order_by(WorkflowRequest.created_at.desc())
        )
        all_active = result.scalars().all()

    actionable = []
    for req in all_active:
        wf = settings.workflows.get(req.type)
        if wf is None:
            continue
        step = get_current_step_config(req, wf)
        if step is None:
            continue

        # Check role-based assignment
        if step.assignee_role and has_role(user, Role(step.assignee_role)):
            actionable.append(req)
            continue
        # Check contextual assignment
        if step.assignee == "target_person" and user.email == req.target_email:
            actionable.append(req)
            continue
        if step.assignee == "requester" and str(user.id) == str(req.created_by):
            actionable.append(req)

    return actionable
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workflow_service.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/workflow_service.py tests/test_workflow_service.py
git commit -m "feat: implement workflow service layer with create, submit, save_draft, and list operations"
```

---

### Task 6: Wire Up and Integration Test

**Files:**
- Modify: `not_dot_net/app.py` (ensure workflow models are registered)
- Modify: `not_dot_net/frontend/shell.py` (temporary: remove Onboarding tab reference if not already done)
- Run full test suite and verify the app starts

- [ ] **Step 1: Verify app.py no longer references onboarding router**

Check that `not_dot_net/app.py` does not import `onboarding_router`. If Task 3 Step 8 was done correctly, this is already clean.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 3: Manual smoke test**

Run: `uv run not-dot-net serve --seed-fake-users`
Verify:
- App starts without errors
- Login works
- People directory still works
- Onboarding tab is gone (will return as Dashboard in Plan 3)

- [ ] **Step 4: Commit if any changes were needed**

```bash
git add -A
git commit -m "chore: integration cleanup after workflow engine implementation"
```

---

## What's Next

**Plan 2: Mail + Notifications** (`2026-03-22-workflow-notifications.md`)
- `backend/mail.py` — async SMTP + dev mode
- `backend/notifications.py` — event-driven notification engine + templates
- Wire notifications into `workflow_service.py` transitions

**Plan 3: Dashboard & UI** (`2026-03-22-workflow-ui.md`)
- `frontend/dashboard.py` — My Requests + Awaiting Action
- `frontend/new_request.py` — workflow type picker + first step form
- `frontend/workflow_step.py` — form/approval step renderer
- `frontend/workflow_token.py` — standalone token page
- `frontend/shell.py` — new tab structure with role-based visibility
- `frontend/i18n.py` — workflow translation keys
