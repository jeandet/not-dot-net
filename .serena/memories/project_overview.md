# Project: not-dot-net

**Purpose:** LPP (Laboratoire de Physique des Plasmas) intranet — NiceGUI frontend, FastAPI-Users for auth (local + LDAP/AD), SQLAlchemy 2.x async with PostgreSQL (prod) / SQLite (dev).

**Stack:** 
- Frontend: NiceGUI
- Backend: FastAPI, FastAPI-Users, SQLAlchemy 2.x async
- Database: PostgreSQL (prod), SQLite (dev)
- Auth: Cookie-based (FastAPI-Users), LDAP/AD integration
- Testing: pytest with NiceGUI testing plugin

## Key Architecture Patterns

- **No public REST API** — All FastAPI-Users routers removed; only HTML form login remains
- **Module-level DI** — `backend/db.py`, `backend/users.py` initialize core dependencies
- **DB-backed config** — `ConfigSection[T]` registry per prefix; admin UI renders forms automatically
- **Secrets** — Separate JSON file (`secrets.key`), 0o600 permissions
- **Workflow tokens** — UUID4 regenerated when assigned to `target_person`; never persisted in audit logs
- **Email normalization** — Lowercase on write; case-insensitive lookups
- **Encrypted storage** — AES-256-GCM per file; `access_personal_data` permission gates download

## Code Style

- KISS + functional over imperative
- Data-driven behavior, Pydantic models preferred
- Small, focused functions/classes
- No comment-decorated blocks (extract as functions)
- Self-explanatory code; comments only for algorithm links or non-obvious decisions
- DRY pragmatically (3+ similar lines)

## Testing

- NiceGUI testing plugin (`nicegui.testing.User`)
- Test entry point: `not_dot_net/app.py`
- Autouse fixture: in-memory SQLite + dev secrets from `tests/conftest.py`
- 499+ tests in suite
