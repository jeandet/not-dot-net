"""Pure-functional option builders for the workflow editor's smart pickers.

No NiceGUI imports — keep this testable in isolation.
"""

import re
from typing import Mapping

from not_dot_net.backend.permissions import PermissionInfo
from not_dot_net.backend.roles import RoleDefinition


def assignee_options(
    roles: Mapping[str, RoleDefinition],
    permissions: Mapping[str, PermissionInfo],
) -> list[dict]:
    """Build labeled options for the step assignee two-step picker.

    Returns dicts of shape:
        {"value": str, "label": str, "kind": str}
    """
    out: list[dict] = []
    for key, definition in sorted(roles.items()):
        out.append({
            "value": f"role:{key}",
            "label": f"Anyone with role: {definition.label or key}",
            "kind": "role",
        })
    for key, info in sorted(permissions.items()):
        out.append({
            "value": f"permission:{key}",
            "label": f"Anyone with permission: {info.label or key}",
            "kind": "permission",
        })
    out.append({
        "value": "contextual:requester",
        "label": "The person who created the request",
        "kind": "contextual_requester",
    })
    out.append({
        "value": "contextual:target_person",
        "label": "The person this request is about",
        "kind": "contextual_target_person",
    })
    return out


def recipient_options(
    roles: Mapping[str, RoleDefinition],
    permissions: Mapping[str, PermissionInfo],
) -> list[dict]:
    """Build labeled options for the notification recipients multi-select."""
    out: list[dict] = [
        {"value": "requester", "label": "Requester",
         "group": "People in this request"},
        {"value": "target_person", "label": "Target person",
         "group": "People in this request"},
    ]
    for key, definition in sorted(roles.items()):
        out.append({
            "value": key,
            "label": f"Role: {definition.label or key}",
            "group": "Roles",
        })
    for key, info in sorted(permissions.items()):
        out.append({
            "value": f"permission:{key}",
            "label": f"Permission: {info.label or key}",
            "group": "Permissions",
        })
    return out


def event_options() -> list[dict]:
    """Build labeled options for the event trigger multi-select."""
    return [
        {"value": "submit", "label": "When submitted"},
        {"value": "approve", "label": "When approved"},
        {"value": "reject", "label": "When rejected"},
        {"value": "request_corrections", "label": "When changes are requested"},
        {"value": "cancel", "label": "When cancelled"},
    ]


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _slugify(label: str, taken: set[str]) -> str:
    """Generate a unique snake_case identifier from a display label.

    Lowercase ASCII; non-alphanumeric runs collapse to underscore; trailing
    underscores stripped. If the result is empty, falls back to `field_<n>`
    where n is the smallest positive integer not already in `taken`.
    Dedup with `_2`, `_3`, etc. against `taken`.
    """
    base = _NON_ALNUM.sub("_", label.lower()).strip("_")
    if not base:
        n = 1
        while f"field_{n}" in taken:
            n += 1
        return f"field_{n}"
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"
