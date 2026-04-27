import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from not_dot_net.backend.db import Base
import not_dot_net.backend.db as db_module
from not_dot_net.backend.secrets import AppSecrets
from not_dot_net.backend.users import init_user_secrets


@pytest.fixture(autouse=True)
async def setup_db():
    """Set up an in-memory SQLite DB and dev secrets for each test."""
    init_user_secrets(AppSecrets(jwt_secret="test-secret-that-is-long-enough-for-hs256", storage_secret="test-storage", file_encryption_key="test-file-encryption-key-32bytes!"))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session
