# AGENTS.md

**not-dot-net** — LPP intranet. NiceGUI frontend, FastAPI-Users cookie auth (local + LDAP/AD), SQLAlchemy 2.x async, PostgreSQL prod / SQLite dev.

## Commands

```bash
uv run python -m not_dot_net.cli serve              # dev (no DATABASE_URL → auto-detect)
DATABASE_URL=postgresql+asyncpg://... uv run python -m not_dot_net.cli serve --secrets-file /secrets/secrets.key
uv run python -m not_dot_net.cli migrate             # Alembic → head
uv run python -m not_dot_net.cli create-user <email> <password> --role admin
uv run python -m not_dot_net.cli promote|revoke|drop-user <email>
uv run pytest                                        # nicegui.testing.User plugin, in-mem SQLite
```

## Quirks

- **Dev mode = absence of `DATABASE_URL`** env var, not a flag. SQLite + auto-create tables + auto-admin.
- **Secrets auto-generated in dev** (`secrets.key`). Missing in prod → `SystemExit(1)`.
- **No public REST API.** All FastAPI-Users routers removed. Only `/auth/login`, `/logout`, `/workflow/token/{token}`, `/workflow/request/{id}`, `/pages/{slug}` remain. No JWT endpoints.
- **CSRF middleware exists in `backend/csrf.py` but is DISABLED** — NiceGUI ASGI compat issue, known as BACKLOG #30.
- **Side-effect imports register config sections.** `import not_dot_net.backend.auth.ldap  # noqa: F401`. Same for `ad_account_config`, `workflow_effects`. Models too: `import not_dot_net.backend.workflow_models  # noqa: F401`.
- **`__mp_main__` guard** — `if __name__ in {"__main__", "__mp_main__"}:` for NiceGUI multiprocessing reload.
- **Email is queued** via `mail_outbox` table, drained by background worker. Dev: only logged, not sent (`dev_catch_all`).
- **LDAP connections cached per-user** with 30-min TTL + background reaper. Overridable via `set_ldap_connect()` for tests.
- **Migrations run synchronously before event loop** in prod (`run_upgrade`). Dev uses `Base.metadata.create_all` on startup.
- **No CI, no pre-commit.** Only quality check is a minimal Ruff (`NPY201` only) + pytest suite. Agent should self-verify.

## Conventions

- **Config:** `section("prefix", PydanticModel, label="...")` from `backend.app_config`. Get/set/reset via async calls.
- **Permissions:** `permission("key", "Label", "Desc")` from `backend.permissions`. Guard with `check_permission(user, perm)`.
- **DB (non-DI):** `session_scope()` context manager from `backend.db`.
- **i18n:** `t("key", **placeholders)` from `frontend.i18n`.
- **Emails normalised to lowercase** on write; lookups are case-insensitive.

## Testing

- **pytest config** in `pyproject.toml`: `asyncio_mode = "auto"`, `main_file = "not_dot_net/app.py"`, plugin `-p nicegui.testing.user_plugin`.
- **`tests/conftest.py`** autouse: in-memory SQLite (FK enforcement), replaces global `db_module._engine`/`_async_session_maker`, restores after test. `mock_ad_effects` fixture available.
- **Init secrets for tests:** `init_user_secrets(AppSecrets(jwt_secret="test-secret-that-is-long-enough-for-hs256", storage_secret="test-storage", file_encryption_key="test-file-encryption-key-32bytes!"))`.

## Key files

| File | Role |
|---|---|
| `not_dot_net/app.py` | App factory, bootstrap orchestration |
| `not_dot_net/cli.py` | Cyclopts CLI commands |
| `not_dot_net/backend/db.py` | DB init, sessions, User model |
| `not_dot_net/backend/users.py` | FastAPI-Users wiring |
| `not_dot_net/backend/app_config.py` | ConfigSection registry |
| `not_dot_net/backend/secrets.py` | AppSecrets management |
| `not_dot_net/backend/permissions.py` | Permission registry |
| `alembic/versions/` | 13 migrations (0001-0013) |
