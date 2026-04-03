# Config-to-DB Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace YAML/pydantic-settings config with DB-stored config sections, secrets file, and admin UI.

**Architecture:** A `ConfigSection[T]` registry in `app_config.py` stores/retrieves Pydantic models as JSON rows in the existing `app_setting` table. Each module owns its config schema. Secrets (JWT, storage) live in a local file. `DATABASE_URL` env var is the only external config. Dev mode auto-generates everything.

**Tech Stack:** SQLAlchemy async, Pydantic BaseModel (not BaseSettings), NiceGUI, cyclopts CLI.

**Spec:** `docs/superpowers/specs/2026-04-03-config-to-db-design.md`

---

## File Structure

After migration:

```
not_dot_net/
  app.py                    # Rewritten startup: secrets file, DB config, first-run
  cli.py                    # --secrets-file, --role on create-user, no --env-file
  config.py                 # Gutted → only Pydantic models for workflows (FieldConfig, etc.) + OrgConfig section
  _dev.py                   # Simplified: no --env-file parsing
  backend/
    app_config.py           # NEW: ConfigSection[T], section(), registry
    secrets.py              # NEW: read/write/generate secrets file
    app_settings.py         # DELETED (merged into app_config.py)
    users.py                # Reads JWT secret from secrets module instead of get_settings()
    mail.py                 # Owns MailConfig section
    workflow_service.py     # Owns WorkflowsConfig section
    workflow_engine.py      # Unchanged (imports types only)
    notifications.py        # Unchanged (imports types only)
    booking_service.py      # Unchanged (no get_settings calls)
    auth/
      ldap.py               # Owns LdapConfig section
  frontend/
    shell.py                # Adds Settings tab for admin
    admin_settings.py       # NEW: admin config UI
    setup_wizard.py         # NEW: first-run setup page
    bookings.py             # Uses bookings config section instead of app_settings
    new_request.py          # Uses workflows config section
    dashboard.py            # Uses workflows config section
    workflow_token.py       # Uses workflows config section
    workflow_step.py        # Uses org config section for teams
```

---

### Task 1: ConfigSection Registry (`app_config.py`)

The core abstraction. No other task can proceed without this.

**Files:**
- Create: `not_dot_net/backend/app_config.py`
- Create: `tests/test_app_config.py`

- [ ] **Step 1: Write failing tests for ConfigSection**

```python
# tests/test_app_config.py
import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from not_dot_net.backend.db import Base
import not_dot_net.backend.db as db_module


class SampleConfig(BaseModel):
    name: str = "default"
    count: int = 42
    tags: list[str] = ["a", "b"]


@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker
    import not_dot_net.backend.app_config  # noqa: F401 — register AppSetting model
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session


async def test_get_returns_defaults_when_no_db_row():
    from not_dot_net.backend.app_config import section
    cfg_section = section("test_default", SampleConfig)
    result = await cfg_section.get()
    assert result == SampleConfig()


async def test_set_then_get_roundtrips():
    from not_dot_net.backend.app_config import section
    cfg_section = section("test_roundtrip", SampleConfig)
    custom = SampleConfig(name="custom", count=99, tags=["x"])
    await cfg_section.set(custom)
    result = await cfg_section.get()
    assert result == custom


async def test_reset_reverts_to_defaults():
    from not_dot_net.backend.app_config import section
    cfg_section = section("test_reset", SampleConfig)
    await cfg_section.set(SampleConfig(name="changed"))
    await cfg_section.reset()
    result = await cfg_section.get()
    assert result == SampleConfig()


async def test_registry_tracks_sections():
    from not_dot_net.backend.app_config import section, get_registry
    cfg_section = section("test_registry", SampleConfig)
    registry = get_registry()
    assert "test_registry" in registry
    assert registry["test_registry"] is cfg_section
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_app_config.py -v`
Expected: ImportError — `app_config` module does not exist.

- [ ] **Step 3: Implement ConfigSection and section()**

```python
# not_dot_net/backend/app_config.py
"""DB-backed config sections with Pydantic schema validation."""

from pydantic import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

from not_dot_net.backend.db import Base, session_scope


class AppSetting(MappedAsDataclass, Base, kw_only=True):
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list] = mapped_column(JSON)


_registry: dict[str, "ConfigSection"] = {}


class ConfigSection[T: BaseModel]:
    def __init__(self, prefix: str, schema: type[T], label: str = ""):
        self.prefix = prefix
        self.schema = schema
        self.label = label or prefix.replace("_", " ").title()

    async def get(self) -> T:
        async with session_scope() as session:
            row = await session.get(AppSetting, self.prefix)
            if row is None:
                return self.schema()
            return self.schema.model_validate(row.value)

    async def set(self, value: T) -> None:
        data = value.model_dump(mode="json")
        async with session_scope() as session:
            row = await session.get(AppSetting, self.prefix)
            if row:
                row.value = data
            else:
                session.add(AppSetting(key=self.prefix, value=data))
            await session.commit()

    async def reset(self) -> None:
        async with session_scope() as session:
            row = await session.get(AppSetting, self.prefix)
            if row:
                await session.delete(row)
                await session.commit()


def section[T: BaseModel](prefix: str, schema: type[T], label: str = "") -> ConfigSection[T]:
    s = ConfigSection(prefix, schema, label)
    _registry[prefix] = s
    return s


def get_registry() -> dict[str, ConfigSection]:
    return _registry
```

**Important:** Since `AppSetting` is now defined here, you must also update `app_settings.py` to import it from `app_config` instead of defining its own copy (SQLAlchemy doesn't allow two ORM classes for the same table on the same `Base`). Replace the model definition in `app_settings.py` with:

```python
from not_dot_net.backend.app_config import AppSetting  # noqa: F401 — re-export
```

And update `db.py` `create_db_and_tables` to import `app_config` instead of (or in addition to) `app_settings`:

```python
import not_dot_net.backend.app_config  # noqa: F401 — register AppSetting with Base
```

Remove the old `import not_dot_net.backend.app_settings` line from `create_db_and_tables`. The `app_settings` module still works because it imports `AppSetting` from `app_config`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app_config.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/app_config.py tests/test_app_config.py
git commit -m "feat: add ConfigSection registry for DB-backed config"
```

---

### Task 2: Secrets File (`secrets.py`)

Handles reading, writing, and generating the secrets file.

**Files:**
- Create: `not_dot_net/backend/secrets.py`
- Create: `tests/test_secrets.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_secrets.py
import json
import os
import stat
import pytest
from pathlib import Path


@pytest.fixture
def tmp_secrets(tmp_path):
    return tmp_path / "secrets.key"


def test_generate_creates_file_with_correct_permissions(tmp_secrets):
    from not_dot_net.backend.secrets import generate_secrets_file
    generate_secrets_file(tmp_secrets)
    assert tmp_secrets.exists()
    mode = stat.S_IMODE(tmp_secrets.stat().st_mode)
    assert mode == 0o600


def test_generate_creates_valid_json_with_both_keys(tmp_secrets):
    from not_dot_net.backend.secrets import generate_secrets_file
    generate_secrets_file(tmp_secrets)
    data = json.loads(tmp_secrets.read_text())
    assert "jwt_secret" in data
    assert "storage_secret" in data
    assert len(data["jwt_secret"]) >= 32
    assert len(data["storage_secret"]) >= 32


def test_read_returns_secrets(tmp_secrets):
    from not_dot_net.backend.secrets import generate_secrets_file, read_secrets_file
    generate_secrets_file(tmp_secrets)
    secrets = read_secrets_file(tmp_secrets)
    assert secrets.jwt_secret
    assert secrets.storage_secret


def test_read_missing_file_raises(tmp_secrets):
    from not_dot_net.backend.secrets import read_secrets_file
    with pytest.raises(SystemExit):
        read_secrets_file(tmp_secrets)


def test_load_or_create_generates_on_first_run(tmp_secrets):
    from not_dot_net.backend.secrets import load_or_create
    secrets = load_or_create(tmp_secrets, dev_mode=False)
    assert secrets.jwt_secret
    assert tmp_secrets.exists()


def test_load_or_create_reads_on_subsequent_run(tmp_secrets):
    from not_dot_net.backend.secrets import load_or_create
    first = load_or_create(tmp_secrets, dev_mode=False)
    second = load_or_create(tmp_secrets, dev_mode=False)
    assert first == second


def test_load_or_create_dev_mode_regenerates_if_missing(tmp_secrets):
    from not_dot_net.backend.secrets import load_or_create
    secrets = load_or_create(tmp_secrets, dev_mode=True)
    assert secrets.jwt_secret
    # Delete and regenerate silently in dev mode
    tmp_secrets.unlink()
    secrets2 = load_or_create(tmp_secrets, dev_mode=True)
    assert secrets2.jwt_secret
    assert secrets2.jwt_secret != secrets.jwt_secret


def test_load_or_create_prod_mode_refuses_if_deleted(tmp_secrets):
    from not_dot_net.backend.secrets import load_or_create
    load_or_create(tmp_secrets, dev_mode=False)
    tmp_secrets.unlink()
    # Create a marker to indicate this isn't a first run
    # (in prod, the DB would already have tables/users)
    with pytest.raises(SystemExit):
        read_secrets_file = __import__("not_dot_net.backend.secrets", fromlist=["read_secrets_file"]).read_secrets_file
        read_secrets_file(tmp_secrets)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: ImportError — `secrets` module does not exist.

- [ ] **Step 3: Implement secrets module**

```python
# not_dot_net/backend/secrets.py
"""Secrets file management — read, write, generate."""

import json
import logging
import os
import secrets
import sys
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger("not_dot_net.secrets")


class AppSecrets(BaseModel):
    jwt_secret: str
    storage_secret: str


def generate_secrets_file(path: Path) -> AppSecrets:
    app_secrets = AppSecrets(
        jwt_secret=secrets.token_urlsafe(32),
        storage_secret=secrets.token_urlsafe(32),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app_secrets.model_dump(), indent=2))
    os.chmod(path, 0o600)
    logger.info("Generated secrets file: %s", path)
    return app_secrets


def read_secrets_file(path: Path) -> AppSecrets:
    if not path.exists():
        logger.error("Secrets file not found: %s", path)
        sys.exit(1)
    data = json.loads(path.read_text())
    return AppSecrets.model_validate(data)


def load_or_create(path: Path, dev_mode: bool) -> AppSecrets:
    if path.exists():
        return read_secrets_file(path)
    if dev_mode:
        logger.info("Dev mode: generating secrets file %s", path)
        return generate_secrets_file(path)
    # First run in production — generate
    if not path.exists():
        logger.info("First run: generating secrets file %s", path)
        return generate_secrets_file(path)
    return read_secrets_file(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_secrets.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/secrets.py tests/test_secrets.py
git commit -m "feat: add secrets file management"
```

---

### Task 3: Define Config Sections in Their Owner Modules

Move config schemas out of `config.py` into the modules that own them, and register sections.

**Files:**
- Modify: `not_dot_net/config.py`
- Modify: `not_dot_net/backend/auth/ldap.py`
- Modify: `not_dot_net/backend/mail.py`
- Modify: `not_dot_net/backend/workflow_service.py`
- Modify: `not_dot_net/frontend/bookings.py`
- Create: `tests/test_config_sections.py`

- [ ] **Step 1: Write failing tests for config sections**

```python
# tests/test_config_sections.py
"""Test that all config sections are registered and return correct defaults."""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from not_dot_net.backend.db import Base
import not_dot_net.backend.db as db_module


@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker
    import not_dot_net.backend.app_settings  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session


async def test_org_config_defaults():
    from not_dot_net.config import org_config, OrgConfig
    result = await org_config.get()
    assert isinstance(result, OrgConfig)
    assert result.app_name == "LPP Intranet"
    assert "Plasma Physics" in result.teams


async def test_ldap_config_defaults():
    from not_dot_net.backend.auth.ldap import ldap_config, LdapConfig
    result = await ldap_config.get()
    assert isinstance(result, LdapConfig)
    assert result.url == "ldap://localhost"


async def test_mail_config_defaults():
    from not_dot_net.backend.mail import mail_config, MailConfig
    result = await mail_config.get()
    assert isinstance(result, MailConfig)
    assert result.dev_mode is True


async def test_workflows_config_defaults():
    from not_dot_net.backend.workflow_service import workflows_config
    result = await workflows_config.get()
    assert "vpn_access" in result.workflows
    assert "onboarding" in result.workflows


async def test_bookings_config_defaults():
    from not_dot_net.config import bookings_config, BookingsConfig
    result = await bookings_config.get()
    assert isinstance(result, BookingsConfig)
    assert "Windows" in result.os_choices
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_sections.py -v`
Expected: ImportError — `org_config` does not exist in config module.

- [ ] **Step 3: Rewrite `config.py` — keep Pydantic models, add OrgConfig and BookingsConfig sections, remove Settings class**

Replace the contents of `not_dot_net/config.py` with:

```python
# not_dot_net/config.py
"""Config models and org/bookings config sections.

Workflow-specific models (FieldConfig, WorkflowStepConfig, etc.) stay here
because they are imported by multiple modules (engine, notifications, frontend).
"""

from pydantic import BaseModel

from not_dot_net.backend.app_config import section


# --- Shared workflow config models (used by engine, notifications, frontend) ---

class FieldConfig(BaseModel):
    name: str
    type: str  # text, email, textarea, date, select, file
    required: bool = False
    label: str = ""
    options_key: str | None = None


class NotificationRuleConfig(BaseModel):
    event: str
    step: str | None = None
    notify: list[str]


class WorkflowStepConfig(BaseModel):
    key: str
    type: str  # form, approval
    assignee_role: str | None = None
    assignee: str | None = None
    fields: list[FieldConfig] = []
    actions: list[str] = []
    partial_save: bool = False


class WorkflowConfig(BaseModel):
    label: str
    start_role: str = "staff"
    target_email_field: str | None = None
    steps: list[WorkflowStepConfig]
    notifications: list[NotificationRuleConfig] = []


# --- Org config section ---

class OrgConfig(BaseModel):
    app_name: str = "LPP Intranet"
    teams: list[str] = [
        "Plasma Physics",
        "Instrumentation",
        "Space Weather",
        "Theory & Simulation",
        "Administration",
    ]
    sites: list[str] = ["Palaiseau", "Jussieu"]
    allowed_origins: list[str] = []


org_config = section("org", OrgConfig, label="Organization")


# --- Bookings config section ---

class BookingsConfig(BaseModel):
    os_choices: list[str] = ["Windows", "Ubuntu", "Fedora"]
    software_tags: dict[str, list[str]] = {
        "Windows": ["Office 365", "MATLAB", "IDL", "Python (Anaconda)", "LabVIEW", "SolidWorks"],
        "Ubuntu": ["Python", "MATLAB", "IDL", "GCC", "LaTeX", "Docker"],
        "Fedora": ["Python", "MATLAB", "IDL", "GCC", "LaTeX", "Docker", "Toolbox"],
    }


bookings_config = section("bookings", BookingsConfig, label="Bookings")
```

- [ ] **Step 4: Add LdapConfig section to `backend/auth/ldap.py`**

At the top of `not_dot_net/backend/auth/ldap.py`, after the existing imports, replace the `get_settings` import and add:

```python
from not_dot_net.backend.app_config import section

class LdapConfig(BaseModel):
    url: str = "ldap://localhost"
    domain: str = "example.com"
    base_dn: str = "dc=example,dc=com"
    port: int = 389

ldap_config = section("ldap", LdapConfig, label="LDAP / Active Directory")
```

Remove `from not_dot_net.config import get_settings, LDAPSettings`.

Update the `default_ldap_connect` signature to accept `LdapConfig` instead of `LDAPSettings`, and `ldap_authenticate` similarly.

Update `ldap_login` endpoint body:
```python
    cfg = await ldap_config.get()
    email = ldap_authenticate(credentials.username, credentials.password, cfg, _ldap_connect)
```

- [ ] **Step 5: Add MailConfig section to `backend/mail.py`**

Replace the contents of `not_dot_net/backend/mail.py`:

```python
"""Async mail sending with dev-mode logging."""

import logging
from email.message import EmailMessage

import aiosmtplib
from pydantic import BaseModel

from not_dot_net.backend.app_config import section

logger = logging.getLogger("not_dot_net.mail")


class MailConfig(BaseModel):
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_tls: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = "noreply@not-dot-net.dev"
    dev_mode: bool = True
    dev_catch_all: str = ""


mail_config = section("mail", MailConfig, label="Email / SMTP")


async def send_mail(
    to: str,
    subject: str,
    body_html: str,
    mail_settings: MailConfig,
) -> None:
    effective_to = to
    if mail_settings.dev_catch_all:
        effective_to = mail_settings.dev_catch_all

    if mail_settings.dev_mode:
        logger.info("[MAIL dev] To: %s (original: %s) Subject: %s", effective_to, to, subject)
        return

    msg = EmailMessage()
    msg["From"] = mail_settings.from_address
    msg["To"] = effective_to
    msg["Subject"] = subject
    msg.set_content(body_html, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=mail_settings.smtp_host,
        port=mail_settings.smtp_port,
        start_tls=mail_settings.smtp_tls,
        username=mail_settings.smtp_user or None,
        password=mail_settings.smtp_password or None,
    )
```

- [ ] **Step 6: Add WorkflowsConfig section to `backend/workflow_service.py`**

At the top of `not_dot_net/backend/workflow_service.py`, replace:

```python
from not_dot_net.config import get_settings
```

with:

```python
from pydantic import BaseModel
from not_dot_net.backend.app_config import section
from not_dot_net.config import (
    WorkflowConfig,
    WorkflowStepConfig,
    FieldConfig,
    NotificationRuleConfig,
)
```

Add the config section after imports:

```python
class WorkflowsConfig(BaseModel):
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
                        FieldConfig(name="end_date", type="date", required=False, label="End Date"),
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


workflows_config = section("workflows", WorkflowsConfig, label="Workflows")
```

Replace `_get_workflow_config`:

```python
async def _get_workflow_config(workflow_type: str) -> WorkflowConfig:
    cfg = await workflows_config.get()
    wf = cfg.workflows.get(workflow_type)
    if wf is None:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
    return wf
```

**Important:** This changes `_get_workflow_config` from sync to async. Update all call sites in this file:
- `create_request`: `wf = await _get_workflow_config(workflow_type)`
- `submit_step`: `wf = await _get_workflow_config(req.type)`
- `save_draft`: `wf = await _get_workflow_config(req.type)`
- `list_actionable`: replace the body (see next sub-step)

Update `_fire_notifications` — replace `settings = get_settings()` and `settings.mail` with:

```python
    from not_dot_net.backend.mail import mail_config
    mail_cfg = await mail_config.get()
```

And pass `mail_settings=mail_cfg` to `notify()`.

Update `list_actionable` — replace `settings = get_settings()` with:

```python
    cfg = await workflows_config.get()
    ...
    for wf_type, wf in cfg.workflows.items():
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_config_sections.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add not_dot_net/config.py not_dot_net/backend/auth/ldap.py not_dot_net/backend/mail.py \
  not_dot_net/backend/workflow_service.py tests/test_config_sections.py
git commit -m "feat: define config sections in owner modules"
```

---

### Task 4: Update Frontend Modules to Use Config Sections

Replace all `get_settings()` calls in frontend code.

**Files:**
- Modify: `not_dot_net/frontend/new_request.py`
- Modify: `not_dot_net/frontend/dashboard.py`
- Modify: `not_dot_net/frontend/workflow_token.py`
- Modify: `not_dot_net/frontend/workflow_step.py`
- Modify: `not_dot_net/frontend/bookings.py`

- [ ] **Step 1: Update `frontend/new_request.py`**

Replace:
```python
from not_dot_net.config import get_settings
```
with:
```python
from not_dot_net.backend.workflow_service import workflows_config
```

The `render` function must become async because `workflows_config.get()` is async. Change:
```python
def render(user: User):
    settings = get_settings()
    ...
    for wf_key, wf_config in settings.workflows.items():
```
to:
```python
async def render(user: User):
    cfg = await workflows_config.get()
    ...
    for wf_key, wf_config in cfg.workflows.items():
```

- [ ] **Step 2: Update `frontend/dashboard.py`**

Replace:
```python
from not_dot_net.config import get_settings
```
with:
```python
from not_dot_net.backend.workflow_service import workflows_config
```

Update `_workflow_labels` to async:
```python
async def _workflow_labels() -> dict[str, str]:
    cfg = await workflows_config.get()
    return {k: wf.label for k, wf in cfg.workflows.items()}
```

Update all call sites of `_workflow_labels()` and `get_settings()` in this file to use `await`. For `get_settings().workflows.get(...)` calls, use `cfg = await workflows_config.get()` then `cfg.workflows.get(...)`.

- [ ] **Step 3: Update `frontend/workflow_token.py`**

Replace:
```python
from not_dot_net.config import get_settings
```
with:
```python
from not_dot_net.backend.workflow_service import workflows_config
```

In `token_page`:
```python
        cfg = await workflows_config.get()
        wf = cfg.workflows.get(req.type)
```

- [ ] **Step 4: Update `frontend/workflow_step.py` `_resolve_options`**

Replace:
```python
def _resolve_options(options_key: str | None) -> list[str]:
    if not options_key:
        return []
    from not_dot_net.config import get_settings
    settings = get_settings()
    if options_key == "teams":
        return settings.teams
    if options_key == "roles":
        from not_dot_net.backend.roles import Role
        return [r.value for r in Role]
    return []
```

with an async version:
```python
async def _resolve_options(options_key: str | None) -> list[str]:
    if not options_key:
        return []
    if options_key == "teams":
        from not_dot_net.config import org_config
        cfg = await org_config.get()
        return cfg.teams
    if options_key == "roles":
        from not_dot_net.backend.roles import Role
        return [r.value for r in Role]
    return []
```

Update all callers of `_resolve_options` in this file to `await`.

- [ ] **Step 5: Update `frontend/bookings.py`**

Replace:
```python
from not_dot_net.config import get_settings
```

Remove this import. The file already imports from `app_settings` — those calls will be updated in a later task when `app_settings` is removed. For now, replace the `get_settings().sites` calls:

```python
from not_dot_net.config import org_config
```

Replace `get_settings().sites` with:
```python
cfg = await org_config.get()
sites = cfg.sites
```

This requires making the calling functions async if not already.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (existing tests still use `init_settings()` which is temporarily kept).

- [ ] **Step 7: Commit**

```bash
git add not_dot_net/frontend/
git commit -m "refactor: update frontend modules to use config sections"
```

---

### Task 5: Update `users.py` to Use Secrets Module

Replace the `get_settings().jwt_secret` calls with a module-level secrets accessor.

**Files:**
- Modify: `not_dot_net/backend/users.py`

- [ ] **Step 1: Add secrets accessor to `users.py`**

The secrets are loaded once at startup and stored in a module-level variable. Add to `not_dot_net/backend/users.py`:

```python
from not_dot_net.backend.secrets import AppSecrets
```

Remove:
```python
from not_dot_net.config import get_settings
```

Add a module-level secrets holder:

```python
_secrets: AppSecrets | None = None


def init_user_secrets(secrets: AppSecrets) -> None:
    global _secrets
    _secrets = secrets


def _get_secret() -> str:
    if _secrets is None:
        raise RuntimeError("Secrets not initialized — call init_user_secrets() first")
    return _secrets.jwt_secret
```

Update `UserManager`:
```python
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    @property
    def reset_password_token_secret(self):
        return _get_secret()

    @property
    def verification_token_secret(self):
        return _get_secret()
```

Update `get_jwt_strategy`:
```python
def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    return JWTStrategy(secret=_get_secret(), lifetime_seconds=3600)
```

Update `ensure_default_admin` — it currently reads `settings.admin_email/password`. This will be handled differently: in dev mode, `app.py` will pass the admin credentials. Change signature:

```python
async def ensure_default_admin(email: str, password: str) -> None:
    """Create default admin user if it doesn't exist yet."""
    from not_dot_net.backend.db import session_scope, get_user_db
    from not_dot_net.backend.schemas import UserCreate
    from fastapi_users.exceptions import UserAlreadyExists

    async with session_scope() as session:
        async with asynccontextmanager(get_user_db)(session) as user_db:
            async with asynccontextmanager(get_user_manager)(user_db) as user_manager:
                try:
                    user = await user_manager.create(
                        UserCreate(
                            email=email,
                            password=password,
                            is_active=True,
                            is_superuser=True,
                        )
                    )
                    user.role = Role.ADMIN
                    session.add(user)
                    await session.commit()
                    logger.info("Default admin '%s' created", email)
                except UserAlreadyExists:
                    pass
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest -v`
Expected: Some tests may fail if they depend on `get_settings()` in users.py. These will be fixed in Task 7.

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/backend/users.py
git commit -m "refactor: users.py reads secrets from secrets module"
```

---

### Task 6: Rewrite Startup (`app.py`, `cli.py`, `_dev.py`)

The main integration point: new startup flow, CLI changes, dev mode.

**Files:**
- Modify: `not_dot_net/app.py`
- Modify: `not_dot_net/cli.py`
- Modify: `not_dot_net/_dev.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Rewrite `app.py`**

```python
# not_dot_net/app.py
import logging
import os
from pathlib import Path
from typing import Optional

from nicegui import app, ui

from not_dot_net.backend.db import init_db, create_db_and_tables
from not_dot_net.backend.secrets import load_or_create
from not_dot_net.backend.users import (
    fastapi_users,
    jwt_backend,
    cookie_backend,
    init_user_secrets,
    ensure_default_admin,
)
from not_dot_net.backend.schemas import UserRead, UserUpdate
from not_dot_net.backend.auth import router as auth_router
from not_dot_net.frontend.login import setup as setup_login
from not_dot_net.frontend.shell import setup as setup_shell
from not_dot_net.frontend.workflow_token import setup as setup_token


DEV_DB_URL = "sqlite+aiosqlite:///./dev.db"
DEV_ADMIN_EMAIL = "admin@not-dot-net.dev"
DEV_ADMIN_PASSWORD = "admin"


def create_app(
    secrets_file: str = "./secrets.key",
    _seed_fake_users: bool = False,
):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    database_url = os.environ.get("DATABASE_URL", DEV_DB_URL)
    dev_mode = "DATABASE_URL" not in os.environ

    init_db(database_url)
    secrets = load_or_create(Path(secrets_file), dev_mode=dev_mode)
    init_user_secrets(secrets)

    async def startup():
        await create_db_and_tables()
        if dev_mode:
            await ensure_default_admin(DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD)
        if _seed_fake_users:
            from not_dot_net.backend.seeding import seed_fake_users
            await seed_fake_users()

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

    from not_dot_net.frontend.i18n import validate_translations
    validate_translations()

    setup_login()
    setup_shell()
    setup_token()


def main(
    host: str = "localhost",
    port: int = 8088,
    secrets_file: str = "./secrets.key",
    seed_fake_users: bool = False,
) -> None:
    create_app(secrets_file, _seed_fake_users=seed_fake_users)
    from not_dot_net.backend.secrets import read_secrets_file
    secrets = read_secrets_file(Path(secrets_file))
    ui.run(
        storage_secret=secrets.storage_secret,
        host=host, port=port, reload=False, title="NotDotNet",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
```

- [ ] **Step 2: Rewrite `cli.py`**

```python
# not_dot_net/cli.py
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from cyclopts import App

app = App(name="NotDotNet", version="0.1.0")


@app.command
def serve(
    host: str = "localhost",
    port: int = 8088,
    secrets_file: str = "./secrets.key",
    seed_fake_users: bool = False,
):
    """Serve the NotDotNet application."""
    from not_dot_net.app import main

    main(host, port, secrets_file, seed_fake_users=seed_fake_users)


@app.command
def create_user(
    username: str,
    password: str,
    role: str = "member",
    secrets_file: str = "./secrets.key",
):
    """Create a new user."""

    async def _create():
        from pathlib import Path
        from not_dot_net.backend.db import init_db, create_db_and_tables, session_scope, get_user_db
        from not_dot_net.backend.secrets import load_or_create
        from not_dot_net.backend.users import get_user_manager, init_user_secrets
        from not_dot_net.backend.schemas import UserCreate
        from not_dot_net.backend.roles import Role

        database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
        dev_mode = "DATABASE_URL" not in os.environ

        init_db(database_url)
        secrets = load_or_create(Path(secrets_file), dev_mode=dev_mode)
        init_user_secrets(secrets)
        await create_db_and_tables()

        user_role = Role(role)

        async with session_scope() as session:
            async with asynccontextmanager(get_user_db)(session) as user_db:
                async with asynccontextmanager(get_user_manager)(user_db) as user_manager:
                    user = await user_manager.create(
                        UserCreate(
                            email=username,
                            password=password,
                            is_active=True,
                            is_superuser=(user_role == Role.ADMIN),
                        )
                    )
                    user.role = user_role
                    session.add(user)
                    await session.commit()
                    print(f"User '{user.email}' created with role '{role}'.")

    asyncio.run(_create())


if __name__ in {"__main__", "__mp_main__"}:
    app()
```

- [ ] **Step 3: Simplify `_dev.py`**

```python
# not_dot_net/_dev.py
"""Dev entry point with auto-reload.

Usage: uv run python not_dot_net/_dev.py [--seed-fake-users]
"""
import sys
from pathlib import Path

from not_dot_net.app import create_app
from not_dot_net.backend.secrets import read_secrets_file
from nicegui import ui

create_app(
    secrets_file="./secrets.key",
    _seed_fake_users="--seed-fake-users" in sys.argv,
)
secrets = read_secrets_file(Path("./secrets.key"))
ui.run(
    storage_secret=secrets.storage_secret,
    host="localhost",
    port=8088,
    reload=True,
    title="NotDotNet",
)
```

- [ ] **Step 4: Remove `pydantic-settings` from `pyproject.toml` dependencies**

Remove `"pydantic-settings",` from the `dependencies` list.

- [ ] **Step 5: Delete `not_dot_net/backend/app_settings.py`**

`AppSetting` ORM model and `db.py` imports were already moved to `app_config.py` in Task 1. Just delete the file:

```bash
git rm not_dot_net/backend/app_settings.py
```

- [ ] **Step 6: Update `frontend/bookings.py` — remove old `app_settings` imports**

Replace:
```python
from not_dot_net.backend.app_settings import (
    get_os_choices,
    get_software_tags,
    set_os_choices,
    set_software_tags,
)
```
with:
```python
from not_dot_net.config import bookings_config
```

Update the calls throughout the file:
- `await get_os_choices()` → `(await bookings_config.get()).os_choices`
- `await get_software_tags()` → `(await bookings_config.get()).software_tags`
- `await set_os_choices(choices)` → `await bookings_config.set((await bookings_config.get()).model_copy(update={"os_choices": choices}))`
- `await set_software_tags(tags)` → `await bookings_config.set((await bookings_config.get()).model_copy(update={"software_tags": tags}))`

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: Some tests will fail because they still call `init_settings()`. Those are fixed in the next task.

- [ ] **Step 8: Commit**

```bash
git add not_dot_net/app.py not_dot_net/cli.py not_dot_net/_dev.py \
  not_dot_net/backend/app_config.py not_dot_net/backend/db.py \
  not_dot_net/frontend/bookings.py pyproject.toml
git rm not_dot_net/backend/app_settings.py
git commit -m "feat: rewrite startup to use DB config and secrets file"
```

---

### Task 7: Fix All Tests

Replace `init_settings()` calls in test fixtures with the new DB-only setup.

**Files:**
- Modify: `tests/test_workflow_service.py`
- Modify: `tests/test_booking_service.py`
- Modify: `tests/test_app_settings.py` → rename to `tests/test_app_config.py` (or merge)
- Modify: `tests/test_workflow_notifications_integration.py`
- Modify: `tests/test_user_crud.py`
- Modify: `tests/test_token_expiry.py`
- Modify: `tests/test_auth_endpoints.py`
- Modify: `tests/test_audit.py`
- Modify: `tests/test_model.py`
- Modify: `tests/test_workflow_config.py`
- Modify: `tests/test_ldap.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_mail.py`

- [ ] **Step 1: Create a shared conftest fixture**

Create or update `tests/conftest.py` with a shared DB fixture that replaces `init_settings()`:

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from not_dot_net.backend.db import Base
import not_dot_net.backend.db as db_module
from not_dot_net.backend.secrets import AppSecrets
from not_dot_net.backend.users import init_user_secrets


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up an in-memory SQLite DB and dev secrets for each test."""
    init_user_secrets(AppSecrets(jwt_secret="test-secret", storage_secret="test-storage"))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker

    # Import all models to register them
    import not_dot_net.backend.workflow_models  # noqa: F401
    import not_dot_net.backend.booking_models  # noqa: F401
    import not_dot_net.backend.audit  # noqa: F401
    import not_dot_net.backend.app_config  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session
```

- [ ] **Step 2: Remove `init_settings()` from each test file**

In every test file that has its own `setup_db` fixture calling `init_settings()`, remove both the `init_settings` import and the call. If the file defines its own `setup_db`, remove it entirely (the `conftest.py` autouse fixture handles it). If a test file's fixture does something extra beyond `init_settings()` + DB setup (unlikely), keep that extra logic.

Files to update:
- `tests/test_workflow_service.py` — remove local `setup_db` fixture and `init_settings` import
- `tests/test_booking_service.py` — same
- `tests/test_workflow_notifications_integration.py` — same
- `tests/test_user_crud.py` — same
- `tests/test_token_expiry.py` — same
- `tests/test_auth_endpoints.py` — same
- `tests/test_audit.py` — same

- [ ] **Step 3: Update tests that import from old config module**

- `tests/test_model.py` — remove `from not_dot_net.config import Settings`, the test should work with defaults
- `tests/test_workflow_config.py` — update imports from `not_dot_net.config import Settings, WorkflowStepConfig, WorkflowConfig` → keep `WorkflowStepConfig, WorkflowConfig` (still in config.py), remove `Settings`
- `tests/test_ldap.py` — update `from not_dot_net.config import LDAPSettings` → `from not_dot_net.backend.auth.ldap import LdapConfig` and update references
- `tests/test_notifications.py` — update imports to use new locations for config models
- `tests/test_mail.py` — update `from not_dot_net.config import MailSettings` → `from not_dot_net.backend.mail import MailConfig`

- [ ] **Step 4: Rename/update `tests/test_app_settings.py`**

This file tests `get_os_choices`/`set_os_choices` etc. from the old `app_settings` module. Update it to test the new `bookings_config` section instead:

```python
# tests/test_app_settings.py → keep filename or rename
import pytest

from not_dot_net.config import bookings_config, BookingsConfig


async def test_bookings_config_defaults():
    cfg = await bookings_config.get()
    assert "Windows" in cfg.os_choices
    assert "Ubuntu" in cfg.software_tags


async def test_bookings_config_set_os_choices():
    custom = BookingsConfig(os_choices=["CustomOS"], software_tags={})
    await bookings_config.set(custom)
    cfg = await bookings_config.get()
    assert cfg.os_choices == ["CustomOS"]


async def test_bookings_config_reset():
    custom = BookingsConfig(os_choices=["X"])
    await bookings_config.set(custom)
    await bookings_config.reset()
    cfg = await bookings_config.get()
    assert cfg == BookingsConfig()
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "fix: update all tests to use DB config instead of init_settings"
```

---

### Task 8: Setup Wizard (Production First-Run)

**Files:**
- Create: `not_dot_net/frontend/setup_wizard.py`
- Modify: `not_dot_net/app.py`
- Create: `tests/test_setup_wizard.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_setup_wizard.py
import pytest
from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.roles import Role
from sqlalchemy import select


async def test_has_admin_returns_false_when_no_users():
    from not_dot_net.frontend.setup_wizard import has_admin
    assert await has_admin() is False


async def test_has_admin_returns_true_after_admin_created():
    from not_dot_net.frontend.setup_wizard import has_admin
    from not_dot_net.backend.users import ensure_default_admin
    await ensure_default_admin("admin@test.dev", "password")
    assert await has_admin() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_setup_wizard.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `setup_wizard.py`**

```python
# not_dot_net/frontend/setup_wizard.py
"""First-run setup wizard — shown when no admin user exists (production only)."""

from nicegui import ui
from sqlalchemy import select

from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.roles import Role
from not_dot_net.backend.users import ensure_default_admin
from not_dot_net.config import org_config, OrgConfig
from not_dot_net.frontend.i18n import t


async def has_admin() -> bool:
    async with session_scope() as session:
        result = await session.execute(
            select(User).where(User.role == Role.ADMIN).limit(1)
        )
        return result.scalar_one_or_none() is not None


def setup():
    @ui.page("/setup")
    async def setup_page():
        if await has_admin():
            ui.navigate.to("/login")
            return

        email = ui.input("Admin Email").props("outlined")
        password = ui.input("Admin Password", password=True, password_toggle_button=True).props("outlined")
        app_name = ui.input("Application Name", value="LPP Intranet").props("outlined")

        async def on_submit():
            if not email.value or not password.value:
                ui.notify("Email and password required", color="negative")
                return
            await ensure_default_admin(email.value, password.value)
            if app_name.value:
                cfg = await org_config.get()
                await org_config.set(cfg.model_copy(update={"app_name": app_name.value}))
            ui.navigate.to("/login")

        ui.button("Complete Setup", on_click=on_submit).props("color=primary")
```

- [ ] **Step 4: Wire setup wizard into `app.py`**

In `not_dot_net/app.py`, add import:
```python
from not_dot_net.frontend.setup_wizard import setup as setup_wizard
```

Add after `setup_token()`:
```python
    if not dev_mode:
        setup_wizard()
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_setup_wizard.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/setup_wizard.py not_dot_net/app.py tests/test_setup_wizard.py
git commit -m "feat: add production first-run setup wizard"
```

---

### Task 9: Admin Settings UI

**Files:**
- Create: `not_dot_net/frontend/admin_settings.py`
- Modify: `not_dot_net/frontend/shell.py`
- Modify: `not_dot_net/frontend/i18n.py`

- [ ] **Step 1: Add i18n keys**

In `not_dot_net/frontend/i18n.py`, add to the `en` dict:
```python
        "settings": "Settings",
        "save": "Save",
        "reset_defaults": "Reset to Defaults",
        "settings_saved": "Settings saved",
        "settings_reset": "Settings reset to defaults",
```

And equivalent French translations in the `fr` dict:
```python
        "settings": "Paramètres",
        "save": "Enregistrer",
        "reset_defaults": "Réinitialiser",
        "settings_saved": "Paramètres enregistrés",
        "settings_reset": "Paramètres réinitialisés",
```

- [ ] **Step 2: Implement `admin_settings.py`**

```python
# not_dot_net/frontend/admin_settings.py
"""Admin settings page — auto-generated forms from config registry."""

import json

from nicegui import ui
from pydantic import BaseModel, ValidationError
from yaml import safe_dump, safe_load

from not_dot_net.backend.app_config import get_registry
from not_dot_net.backend.audit import log_audit
from not_dot_net.frontend.i18n import t


def _is_complex(schema: type[BaseModel]) -> bool:
    """Check if a schema has nested models or dicts — use YAML editor."""
    for field_info in schema.model_fields.values():
        annotation = field_info.annotation
        if annotation is dict or (hasattr(annotation, "__origin__") and annotation.__origin__ is dict):
            return True
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return True
    return False


async def render(user):
    """Render the admin settings tab content."""
    registry = get_registry()

    for prefix, cfg_section in sorted(registry.items()):
        current = await cfg_section.get()
        schema = cfg_section.schema

        with ui.expansion(cfg_section.label, icon="settings").classes("w-full"):
            if _is_complex(schema):
                await _render_yaml_editor(prefix, cfg_section, current, user)
            else:
                await _render_form(prefix, cfg_section, current, user)


async def _render_form(prefix, cfg_section, current, user):
    """Auto-generate form fields from Pydantic model."""
    inputs = {}
    schema = cfg_section.schema
    data = current.model_dump()

    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        value = data.get(field_name, field_info.default)

        if annotation is bool:
            inputs[field_name] = ui.switch(field_name, value=value)
        elif annotation is int:
            inputs[field_name] = ui.number(field_name, value=value)
        elif annotation is str:
            inputs[field_name] = ui.input(field_name, value=value).classes("w-full")
        elif annotation == list[str]:
            # Chip editor for list of strings
            inputs[field_name] = ui.input(
                field_name,
                value=", ".join(value) if isinstance(value, list) else str(value),
            ).classes("w-full").tooltip("Comma-separated values")
        else:
            inputs[field_name] = ui.input(field_name, value=str(value)).classes("w-full")

    async def save():
        update = {}
        for field_name, field_info in schema.model_fields.items():
            widget = inputs[field_name]
            annotation = field_info.annotation
            if annotation is bool:
                update[field_name] = widget.value
            elif annotation is int:
                update[field_name] = int(widget.value)
            elif annotation == list[str]:
                update[field_name] = [s.strip() for s in widget.value.split(",") if s.strip()]
            else:
                update[field_name] = widget.value
        try:
            new_config = schema.model_validate(update)
            await cfg_section.set(new_config)
            await log_audit("settings", "update", actor_id=user.id, actor_email=user.email, detail=f"section={prefix}")
            ui.notify(t("settings_saved"), color="positive")
        except ValidationError as e:
            ui.notify(str(e), color="negative")

    async def reset():
        await cfg_section.reset()
        await log_audit("settings", "reset", actor_id=user.id, actor_email=user.email, detail=f"section={prefix}")
        ui.notify(t("settings_reset"), color="info")

    with ui.row():
        ui.button(t("save"), on_click=save).props("color=primary")
        ui.button(t("reset_defaults"), on_click=reset).props("flat color=grey")


async def _render_yaml_editor(prefix, cfg_section, current, user):
    """YAML code editor for complex config sections."""
    yaml_str = safe_dump(current.model_dump(), default_flow_style=False, allow_unicode=True)
    editor = ui.codemirror(yaml_str, language="yaml").classes("w-full").style("min-height: 300px")

    async def save():
        try:
            data = safe_load(editor.value)
            new_config = cfg_section.schema.model_validate(data)
            await cfg_section.set(new_config)
            await log_audit("settings", "update", actor_id=user.id, actor_email=user.email, detail=f"section={prefix}")
            ui.notify(t("settings_saved"), color="positive")
        except Exception as e:
            ui.notify(str(e), color="negative")

    async def reset():
        await cfg_section.reset()
        default = cfg_section.schema()
        editor.value = safe_dump(default.model_dump(), default_flow_style=False, allow_unicode=True)
        await log_audit("settings", "reset", actor_id=user.id, actor_email=user.email, detail=f"section={prefix}")
        ui.notify(t("settings_reset"), color="info")

    with ui.row():
        ui.button(t("save"), on_click=save).props("color=primary")
        ui.button(t("reset_defaults"), on_click=reset).props("flat color=grey")
```

- [ ] **Step 3: Add Settings tab to `shell.py`**

In `not_dot_net/frontend/shell.py`, add import:
```python
from not_dot_net.frontend.admin_settings import render as render_settings
```

Add i18n key usage:
```python
        settings_label = t("settings")
```

Add to `available_tabs` for admin:
```python
        if is_admin:
            available_tabs.append(audit_label)
            available_tabs.append(settings_label)
```

Add tab in header:
```python
                if is_admin:
                    ui.tab(audit_label, icon="policy")
                    ui.tab(settings_label, icon="settings")
```

Add tab panel:
```python
            if is_admin:
                with ui.tab_panel(audit_label):
                    render_audit()
                with ui.tab_panel(settings_label):
                    await render_settings(user)
```

Note: the `main_page` function needs to become async if it isn't already (NiceGUI supports async page handlers).

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/frontend/admin_settings.py not_dot_net/frontend/shell.py \
  not_dot_net/frontend/i18n.py
git commit -m "feat: add admin settings UI with auto-generated forms"
```

---

### Task 10: Cleanup and Final Verification

Remove dead code, verify everything works end-to-end.

**Files:**
- Modify: `not_dot_net/config.py` — remove any leftover dead code (Settings class remnants, init_settings, get_settings)
- Modify: `not_dot_net/backend/seeding.py` — update if it references `get_settings`
- Modify: `pyproject.toml` — add `pyyaml` dependency (for YAML editor in admin settings)

- [ ] **Step 1: Clean up `config.py`**

Verify `config.py` no longer has `Settings`, `init_settings`, `get_settings`, or any pydantic-settings imports. It should only contain the Pydantic model classes (FieldConfig, WorkflowStepConfig, etc.) and the `OrgConfig`/`BookingsConfig` sections.

- [ ] **Step 2: Check `seeding.py` for `get_settings` references**

Run: `grep -n "get_settings\|init_settings" not_dot_net/backend/seeding.py`

If found, update to use the relevant config section.

- [ ] **Step 3: Add `pyyaml` to dependencies in `pyproject.toml`**

Add `"pyyaml"` to the `dependencies` list (needed for `safe_dump`/`safe_load` in admin settings UI). Check if it's already a transitive dependency — if so, still add it explicitly.

- [ ] **Step 4: Verify no remaining references to old config**

Run:
```bash
grep -rn "get_settings\|init_settings\|from not_dot_net.config import Settings\|from not_dot_net.backend.app_settings" \
  not_dot_net/ tests/ --include="*.py"
```

Expected: No matches.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Manual smoke test**

Run: `uv run not-dot-net serve`
- Verify dev mode starts with SQLite
- Verify admin login works (admin@not-dot-net.dev / admin)
- Verify Settings tab appears for admin
- Verify editing a config section works
- Verify secrets.key file was created

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: cleanup dead config code, add pyyaml dependency"
```
