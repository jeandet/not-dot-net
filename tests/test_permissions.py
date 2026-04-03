import pytest

from not_dot_net.backend.permissions import (
    PermissionInfo,
    permission,
    get_permissions,
    _registry,
    has_permissions,
    check_permission,
)
from not_dot_net.backend.roles import RoleDefinition, roles_config


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate registry between tests."""
    saved = dict(_registry)
    _registry.clear()
    yield
    _registry.clear()
    _registry.update(saved)


def test_permission_registers_and_returns_key():
    key = permission("do_thing", "Do Thing", "Can do the thing")
    assert key == "do_thing"
    assert "do_thing" in get_permissions()
    info = get_permissions()["do_thing"]
    assert isinstance(info, PermissionInfo)
    assert info.label == "Do Thing"
    assert info.description == "Can do the thing"


def test_get_permissions_returns_all():
    permission("a", "A")
    permission("b", "B")
    assert set(get_permissions().keys()) == {"a", "b"}


def test_duplicate_registration_overwrites():
    permission("x", "X1")
    permission("x", "X2")
    assert get_permissions()["x"].label == "X2"


async def test_has_permissions_granted():
    cfg = await roles_config.get()
    cfg.roles["tester"] = RoleDefinition(label="Tester", permissions=["perm_a", "perm_b"])
    await roles_config.set(cfg)

    class FakeUser:
        role = "tester"

    assert await has_permissions(FakeUser(), "perm_a") is True
    assert await has_permissions(FakeUser(), "perm_a", "perm_b") is True


async def test_has_permissions_denied():
    cfg = await roles_config.get()
    cfg.roles["limited"] = RoleDefinition(label="Limited", permissions=["perm_a"])
    await roles_config.set(cfg)

    class FakeUser:
        role = "limited"

    assert await has_permissions(FakeUser(), "perm_a", "perm_c") is False


async def test_has_permissions_unknown_role():
    class FakeUser:
        role = "nonexistent"

    assert await has_permissions(FakeUser(), "anything") is False


async def test_check_permission_raises_on_denial():
    class FakeUser:
        role = "nonexistent"

    with pytest.raises(PermissionError):
        await check_permission(FakeUser(), "anything")


async def test_check_permission_passes_when_granted():
    cfg = await roles_config.get()
    cfg.roles["ok_role"] = RoleDefinition(label="OK", permissions=["allowed"])
    await roles_config.set(cfg)

    class FakeUser:
        role = "ok_role"

    await check_permission(FakeUser(), "allowed")  # should not raise
