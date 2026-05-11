import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from not_dot_net.backend.db import Base
import not_dot_net.backend.db as db_module
from not_dot_net.backend.secrets import AppSecrets
from not_dot_net.backend.users import init_user_secrets


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    # Match production PostgreSQL semantics so FK violations surface in tests.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture()
async def mock_ad_effects(monkeypatch):
    """Monkeypatch AD effect handlers to avoid requiring real LDAP credentials in tests."""
    from not_dot_net.backend.workflow_effects import EFFECT_REGISTRY, EffectResult
    
    async def fake_run(request, step, action, params, ad_creds, actor):
        return EffectResult(kind="ad_add_to_groups", succeeded=True)
    
    monkeypatch.setattr(EFFECT_REGISTRY["ad_add_to_groups"], "run", fake_run)


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up an in-memory SQLite DB and dev secrets for each test."""
    init_user_secrets(AppSecrets(jwt_secret="test-secret-that-is-long-enough-for-hs256", storage_secret="test-storage", file_encryption_key="test-file-encryption-key-32bytes!"))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker

    import not_dot_net.backend.workflow_models  # noqa: F401
    import not_dot_net.backend.booking_models  # noqa: F401
    import not_dot_net.backend.audit  # noqa: F401
    import not_dot_net.backend.app_config  # noqa: F401
    import not_dot_net.backend.encrypted_storage  # noqa: F401
    import not_dot_net.backend.tenure_service  # noqa: F401
    import not_dot_net.backend.mail_outbox  # noqa: F401
    import not_dot_net.backend.uid_allocator  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session
