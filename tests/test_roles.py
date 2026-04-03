# tests/test_roles.py
import pytest

from not_dot_net.backend.roles import RoleDefinition, RolesConfig, roles_config


async def test_default_config_has_admin_role():
    cfg = await roles_config.get()
    assert "admin" in cfg.roles
    admin = cfg.roles["admin"]
    assert "manage_roles" in admin.permissions
    assert "manage_settings" in admin.permissions


async def test_set_roles_config():
    cfg = await roles_config.get()
    cfg.roles["staff"] = RoleDefinition(
        label="Staff", permissions=["create_workflows"]
    )
    await roles_config.set(cfg)
    reloaded = await roles_config.get()
    assert "staff" in reloaded.roles
    assert reloaded.roles["staff"].permissions == ["create_workflows"]


async def test_lockout_guard_preserves_admin():
    """Cannot remove admin role or strip its critical permissions."""
    cfg = await roles_config.get()
    del cfg.roles["admin"]
    await roles_config.set(cfg)
    reloaded = await roles_config.get()
    assert "admin" in reloaded.roles
    assert "manage_roles" in reloaded.roles["admin"].permissions
    assert "manage_settings" in reloaded.roles["admin"].permissions


async def test_lockout_guard_restores_stripped_permissions():
    """If admin role exists but lacks critical permissions, they are added back."""
    cfg = await roles_config.get()
    cfg.roles["admin"].permissions = ["some_other_perm"]
    await roles_config.set(cfg)
    reloaded = await roles_config.get()
    assert "manage_roles" in reloaded.roles["admin"].permissions
    assert "manage_settings" in reloaded.roles["admin"].permissions
    assert "some_other_perm" in reloaded.roles["admin"].permissions


async def test_default_role_field():
    cfg = await roles_config.get()
    assert cfg.default_role == ""


from not_dot_net.backend.roles import seed_admin_permissions


async def test_seed_admin_gets_all_permissions():
    # Import modules that declare permissions
    import not_dot_net.backend.booking_service  # noqa: F401
    import not_dot_net.backend.workflow_service  # noqa: F401
    import not_dot_net.frontend.audit_log  # noqa: F401
    import not_dot_net.frontend.directory  # noqa: F401

    await seed_admin_permissions()
    cfg = await roles_config.get()
    admin = cfg.roles["admin"]
    assert "manage_bookings" in admin.permissions
    assert "create_workflows" in admin.permissions
    assert "approve_workflows" in admin.permissions
    assert "view_audit_log" in admin.permissions
    assert "manage_users" in admin.permissions
    assert "manage_roles" in admin.permissions
    assert "manage_settings" in admin.permissions
