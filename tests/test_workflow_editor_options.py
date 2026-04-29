"""Tests for the workflow editor option builders + slugifier."""

from not_dot_net.backend.permissions import PermissionInfo
from not_dot_net.backend.roles import RoleDefinition
from not_dot_net.frontend.workflow_editor_options import (
    _slugify,
    assignee_options,
    event_options,
    recipient_options,
)


_ROLES = {
    "admin": RoleDefinition(label="Administrator", permissions=[]),
    "staff": RoleDefinition(label="Staff", permissions=[]),
}
_PERMS = {
    "approve_workflows": PermissionInfo("approve_workflows", "Approve workflows"),
    "manage_users": PermissionInfo("manage_users", "Manage users"),
}


def test_assignee_options_includes_four_kinds():
    opts = assignee_options(_ROLES, _PERMS)
    kinds = {o["kind"] for o in opts}
    assert kinds == {"role", "permission", "contextual_requester", "contextual_target_person"}


def test_assignee_options_role_value_format():
    opts = assignee_options(_ROLES, _PERMS)
    role_opts = [o for o in opts if o["kind"] == "role"]
    values = sorted(o["value"] for o in role_opts)
    assert values == ["role:admin", "role:staff"]
    labels = [o["label"] for o in role_opts]
    assert all(l.startswith("Anyone with role: ") for l in labels)


def test_assignee_options_contextual_singletons():
    opts = assignee_options(_ROLES, _PERMS)
    contextual_values = {o["value"] for o in opts if o["kind"].startswith("contextual_")}
    assert contextual_values == {"contextual:requester", "contextual:target_person"}


def test_recipient_options_three_groups():
    opts = recipient_options(_ROLES, _PERMS)
    groups = {o["group"] for o in opts}
    assert groups == {
        "People in this request",
        "Roles",
        "Permissions",
    }


def test_recipient_options_value_format():
    opts = recipient_options(_ROLES, _PERMS)
    by_value = {o["value"]: o for o in opts}
    assert "requester" in by_value
    assert "target_person" in by_value
    assert "admin" in by_value
    assert "staff" in by_value
    assert "permission:approve_workflows" in by_value
    assert "permission:manage_users" in by_value


def test_event_options_five_engine_events():
    opts = event_options()
    values = [o["value"] for o in opts]
    assert values == ["submit", "approve", "reject", "request_corrections", "cancel"]
    labels = [o["label"] for o in opts]
    assert labels == [
        "When submitted",
        "When approved",
        "When rejected",
        "When changes are requested",
        "When cancelled",
    ]


def test_slugify_basic():
    assert _slugify("Email Address", taken=set()) == "email_address"


def test_slugify_dedup_two():
    assert _slugify("Email", taken={"email"}) == "email_2"


def test_slugify_dedup_three():
    assert _slugify("Email", taken={"email", "email_2"}) == "email_3"


def test_slugify_empty_falls_back_to_field_n():
    assert _slugify("!!!", taken=set()) == "field_1"
    assert _slugify("", taken={"field_1"}) == "field_2"


def test_slugify_collapses_runs_of_punctuation():
    assert _slugify("First Name (legal)", taken=set()) == "first_name_legal"
