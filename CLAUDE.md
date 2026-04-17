# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is this

**not-dot-net** is a simple intranet application for LPP (Laboratoire de Physique des Plasmas). It uses NiceGUI for the frontend, FastAPI-Users for authentication (local + LDAP), and SQLAlchemy with async SQLite for persistence. Configuration is via pydantic-settings with YAML files.

## Commands

```bash
# Install (uses flit, uv recommended)
uv pip install -e .

# Run the app
uv run python -m not_dot_net.cli serve --host localhost --port 8000 --env-file config.yaml

# Create a user
uv run python -m not_dot_net.cli create-user <email> <password> --env-file config.yaml

# Dump default config
uv run python -m not_dot_net.cli default-config

# Run tests (uses nicegui testing plugin)
uv run pytest
```

## Architecture

### Startup flow

`cli.py serve` → `app.main()` → `create_app(config_file)`:
1. `init_settings()` loads YAML + env config into module-level singleton
2. `init_db()` creates async engine + session maker at module level
3. `app.on_startup(create_db_and_tables)` schedules table creation
4. Login router is included (`/auth/login` HTML form POST, `/logout`)
5. Frontend pages are set up (`/login`, shell tabs, public pages)

**No public REST API.** FastAPI-Users' `get_users_router` exposed `PATCH /users/me` which let any logged-in user set their own `role` to `admin` (custom fields bypass the library's `is_superuser` strip). All FastAPI-Users HTTP routers and the custom `/auth/local` JWT endpoint have been removed — auth backends (`cookie_backend`) are kept only to power the `current_active_user` dependency used by NiceGUI pages.

### Module-level dependency injection

Following idiomatic FastAPI-Users patterns, dependencies are module-level:
- `backend/db.py`: `get_async_session()`, `get_user_db()` — async generators for `Depends()`
- `backend/users.py`: `get_user_manager()`, `current_active_user`, `current_active_user_optional`

Both `db.py` and `config.py` use `init_*()` functions that must be called before dependencies are usable. `create_app()` handles this.

### Auth endpoints

- `frontend/login.py`: POST `/auth/login` (HTML form, local-first then LDAP/AD fallback, sets httponly cookie), GET `/logout`
- `backend/auth/ldap.py`: owns `LdapConfig` section + helpers (no HTTP endpoints)

### Frontend pages

NiceGUI pages in `frontend/` expose a `setup()` function that registers `@ui.page` routes. They import dependencies directly from `backend/users.py`.

### Configuration

`config.py` uses nested Pydantic models under a single `BaseSettings` root. Sources: init args > env vars > YAML file. JWT secret is in `Settings.jwt_secret`.

### Testing

Tests use `nicegui.testing.User` (configured via pytest plugin in pyproject.toml: `-p nicegui.testing.user_plugin`). The test entry point is `main_file = "app.py"` in `[tool.pytest]`.
