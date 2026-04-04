import pytest
from not_dot_net.backend.db import User, session_scope
from sqlalchemy import select


async def test_has_admin_returns_false_when_no_users():
    from not_dot_net.frontend.setup_wizard import has_admin
    assert await has_admin() is False


async def test_has_admin_returns_true_after_admin_created():
    from not_dot_net.frontend.setup_wizard import has_admin
    from not_dot_net.backend.users import ensure_default_admin
    await ensure_default_admin("admin@test.dev", "password")
    assert await has_admin() is True
