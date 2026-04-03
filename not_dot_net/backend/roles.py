"""RBAC role definitions — DB-backed via ConfigSection."""

from pydantic import BaseModel

from not_dot_net.backend.app_config import ConfigSection, section

# Re-export for backward compatibility while other modules are migrated
from not_dot_net.backend.db import Role  # noqa: F401


class RoleDefinition(BaseModel):
    label: str
    permissions: list[str] = []


class RolesConfig(BaseModel):
    default_role: str = ""
    roles: dict[str, RoleDefinition] = {
        "admin": RoleDefinition(
            label="Administrator",
            permissions=["manage_roles", "manage_settings"],
        ),
    }


LOCKOUT_PERMISSIONS = {"manage_roles", "manage_settings"}


class RolesConfigSection(ConfigSection["RolesConfig"]):
    """ConfigSection with lockout guard for the admin role."""

    async def set(self, value: RolesConfig) -> None:
        _enforce_admin_lockout(value)
        await super().set(value)

    async def get(self) -> RolesConfig:
        value = await super().get()
        _enforce_admin_lockout(value)
        return value


def _enforce_admin_lockout(cfg: RolesConfig) -> None:
    """Ensure admin role exists and has critical permissions."""
    if "admin" not in cfg.roles:
        cfg.roles["admin"] = RoleDefinition(
            label="Administrator", permissions=list(LOCKOUT_PERMISSIONS)
        )
    admin = cfg.roles["admin"]
    for perm in LOCKOUT_PERMISSIONS:
        if perm not in admin.permissions:
            admin.permissions.append(perm)


roles_config = RolesConfigSection("roles", RolesConfig, label="Roles")
# Register in the global config registry
from not_dot_net.backend.app_config import _registry
_registry["roles"] = roles_config


async def seed_admin_permissions() -> None:
    """Ensure the admin role has every registered permission."""
    from not_dot_net.backend.permissions import get_permissions
    cfg = await roles_config.get()
    admin = cfg.roles.get("admin")
    if admin is None:
        return
    all_perms = set(get_permissions().keys())
    current = set(admin.permissions)
    if not all_perms.issubset(current):
        admin.permissions = sorted(current | all_perms)
        await roles_config.set(cfg)
