# Suggested Commands

## Development

```bash
# Install
uv pip install -e .

# Run dev server (auto-detects dev mode: no DATABASE_URL → SQLite)
uv run python -m not_dot_net.cli serve --host localhost --port 8088

# Run tests
uv run pytest

# Run specific tests
uv run pytest tests/test_widgets.py -k keyed -v
```

## Database

```bash
# Migrations (production)
uv run python -m not_dot_net.cli migrate
uv run python -m not_dot_net.cli stamp head
```

## User Administration

```bash
uv run python -m not_dot_net.cli create-user <email> <password> --role admin
uv run python -m not_dot_net.cli promote <email|name>
uv run python -m not_dot_net.cli revoke <email|name>
uv run python -m not_dot_net.cli drop-user <email|name>
```
