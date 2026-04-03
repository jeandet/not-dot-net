# Config-to-DB Migration Design

**Goal:** Replace YAML/pydantic-settings configuration with database-stored config, making the app zero-config for dev and single-env-var for production. Secrets persist in a local file, everything else lives in DB and is managed through an admin UI.

---

## 1. Bootstrap & CLI Surface

### CLI

```bash
# Production
DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/intranet" \
  not-dot-net serve --host 0.0.0.0 --port 8000 --secrets-file /etc/not-dot-net/secrets.key

# Dev mode (all defaults)
not-dot-net serve
```

**Arguments:**
- `--host` (default: `localhost`)
- `--port` (default: `8088`)
- `--secrets-file` (default: `./secrets.key`)
- `--seed-fake-users` (unchanged)

**Env vars:**
- `DATABASE_URL` — the only external config. Absence triggers dev mode.

**Dev mode detection:** `DATABASE_URL` not set → use `sqlite+aiosqlite:///./dev.db`.

### Secrets File

A JSON file containing `jwt_secret` and `storage_secret`. Managed automatically:
- **First run:** generated with `secrets.token_urlsafe(32)`, written with `0600` permissions.
- **Subsequent runs:** read from file.
- **Missing file after first run (production):** refuse to start (silent regeneration would invalidate all sessions).
- **Missing file (dev mode):** generate silently — dev sessions are ephemeral.

Format:
```json
{"jwt_secret": "...", "storage_secret": "..."}
```

### Startup Sequence

1. Read `DATABASE_URL` env var (fall back to `sqlite+aiosqlite:///./dev.db`)
2. Connect to DB, `create_all` tables
3. Read secrets file — if missing, generate and persist it
4. Build FastAPI-Users auth backends using secrets
5. Check for admin user → first-run mode if none (see Section 3)
6. Load all registered config sections from DB (defaults fill missing values)
7. Start NiceGUI

### Removed

- `--env-file` argument
- `default-config` CLI command
- `config.yaml` support entirely (no migration path — no existing deployments)

### Kept

- `create-user` CLI command — gains `--role` flag, needs `DATABASE_URL` and `--secrets-file`
- `--seed-fake-users`

---

## 2. Config Section Registry

### Core Abstraction

`not_dot_net/backend/app_config.py` — replaces both `config.py` and `app_settings.py`.

```python
class ConfigSection[T: BaseModel]:
    prefix: str
    schema: type[T]

    async def get(self) -> T        # read from DB, validate, fill defaults
    async def set(self, value: T)   # validate and persist
    async def reset(self)           # delete DB row (reverts to schema defaults)

def section[T: BaseModel](prefix: str, schema: type[T]) -> ConfigSection[T]:
    """Register and return a typed config section accessor."""
```

### Storage

Reuses the existing `app_setting` table (key-value with JSON). One row per section:
- Key = section prefix (e.g. `"ldap"`)
- Value = model dumped to JSON

### How Modules Use It

Each module defines its own config schema and registers a section at module level:

```python
# in backend/auth/ldap.py
class LdapConfig(BaseModel):
    url: str = "ldap://localhost"
    domain: str = "example.com"
    base_dn: str = "dc=example,dc=com"
    port: int = 389

ldap_config = app_config.section("ldap", LdapConfig)

# usage
cfg = await ldap_config.get()
```

### Registry

`section()` stores the `ConfigSection` in a module-level dict. The admin UI iterates registered sections to auto-generate forms. Sections can carry optional metadata (human label, category) for UI grouping.

### Config Sections (from splitting current Settings)

| Prefix | Schema | Owner module | Fields |
|---|---|---|---|
| `org` | `OrgConfig` | `config.py` (or new `org.py`) | app_name, teams, sites, allowed_origins |
| `ldap` | `LdapConfig` | `backend/auth/ldap.py` | url, domain, base_dn, port |
| `mail` | `MailConfig` | `backend/mail.py` | smtp_host, smtp_port, smtp_tls, smtp_user, smtp_password, from_address, dev_mode, dev_catch_all |
| `bookings` | `BookingsConfig` | `backend/booking_service.py` | os_choices, software_tags |
| `workflows` | `WorkflowsConfig` | `backend/workflow_service.py` | dict[str, WorkflowConfig] (reuses existing Pydantic models) |

### What Disappears

- `config.py`'s `Settings` class, `init_settings()`, `get_settings()`
- `app_settings.py` (merged into `app_config.py`)
- `pydantic-settings` and `pydantic-yaml` dependencies

---

## 3. First-Run & Admin Setup

### Dev Mode (no `DATABASE_URL`)

- Auto-create admin user `admin@not-dot-net.dev` / `admin` with `Role.ADMIN`
- All config sections use Pydantic defaults (same experience as today)
- No wizard, no prompts

### Production (explicit `DATABASE_URL`)

- On startup, check if any user with `Role.ADMIN` exists
- If none, serve only a setup wizard at `/setup`:
  - Create admin account (email + password)
  - Basic org settings (app name, teams, sites)
  - LDAP and mail configured later from admin UI
- After setup complete, redirect to login
- `/setup` returns 404 once an admin exists

### CLI Backdoor

For headless/Docker deployments:

```bash
DATABASE_URL="..." not-dot-net create-user admin@lpp.fr s3cret \
  --role admin --secrets-file /etc/not-dot-net/secrets.key
```

---

## 4. Admin Config UI

### Location

New "Settings" tab in the shell, visible to `ADMIN` role only.

### Layout

One collapsible card per registered config section, forms auto-generated from Pydantic model:

| Python type | UI widget |
|---|---|
| `str` | text input |
| `int` | number input |
| `bool` | toggle |
| `list[str]` | chip/tag editor |
| `dict` | JSON editor |
| Nested `BaseModel` | grouped fields |

### Workflow Config

Deeply nested — use a YAML code editor (Monaco/CodeMirror) with validation against `WorkflowsConfig` on save. Auto-generated forms for all other sections. A visual workflow builder can be a future feature.

### Save Flow

Edit → client-side Pydantic validation → POST → server-side re-validation → persist to `app_setting` → audit log entry → success toast.

### Reset

Per-section reset button: deletes the DB row, reverts to Pydantic defaults.

---

## 5. Impact on Existing Code

### Modules That Change

- **`config.py`** — gutted. Becomes either a thin `OrgConfig` section or removed entirely, with `OrgConfig` living in a new module.
- **`app.py`** — startup rewritten: no `init_settings()`, reads secrets file, checks first-run. `create_app()` signature changes (no `config_file`).
- **`cli.py`** — `serve` loses `--env-file`, gains `--secrets-file`. `default-config` removed. `create-user` gains `--role`.
- **`app_settings.py`** — deleted, replaced by `app_config.py`.
- **`backend/auth/ldap.py`** — owns `LdapConfig` section, reads from DB instead of `get_settings()`.
- **`backend/mail.py`** — owns `MailConfig` section.
- **`backend/booking_service.py`** — owns `BookingsConfig` section, replaces `app_settings` calls.
- **`backend/workflow_service.py`** — owns `WorkflowsConfig` section.
- **`frontend/shell.py`** — adds Settings tab for admins.
- **All modules calling `get_settings()`** — switch to their relevant `ConfigSection.get()`.

### New Modules

- **`backend/app_config.py`** — `ConfigSection`, `section()`, registry.
- **`frontend/admin_settings.py`** — admin config UI page.
- **`frontend/setup_wizard.py`** — first-run setup page (production only).

### Tests

- Existing tests that use `init_settings()` need updating to seed config via `ConfigSection.set()` or use defaults.
- New tests for: `ConfigSection` get/set/reset, secrets file generation, first-run detection, setup wizard, admin settings UI.
