# Workflow Editor Friendliness Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace engineer jargon with smart pickers, helper text, and grouped sections in the workflow form editor — no schema or persisted-data changes.

**Architecture:** One new pure-functional helper module (`workflow_editor_options.py`) builds labeled option lists for the smart pickers. The `WorkflowEditorDialog` class is extended in place: assignee + notification widgets are replaced with smart pickers; the field row gets a display-name auto-slug + lock-on-save flow; the YAML tab moves behind a header `</>` button; the workflow right pane is grouped into collapsible sections. ~25 new i18n keys cover the relabeled fields.

**Tech Stack:** NiceGUI (Quasar `q-select`, `q-expansion-item`, `q-badge`), Pydantic v2, existing `RolesConfig` and permission registry.

**Spec:** `docs/superpowers/specs/2026-04-29-workflow-editor-friendliness-design.md`

---

### Task 1: `workflow_editor_options.py` — option builders + slugifier

**Files:**
- Create: `not_dot_net/frontend/workflow_editor_options.py`
- Test: `tests/test_workflow_editor_options.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_editor_options.py
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
```

- [ ] **Step 2: Run tests to verify failure**

```bash
uv run pytest tests/test_workflow_editor_options.py -v
```
Expected: FAIL — `ModuleNotFoundError: not_dot_net.frontend.workflow_editor_options`.

- [ ] **Step 3: Implement the module**

```python
# not_dot_net/frontend/workflow_editor_options.py
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
    """Build the labeled options for the step assignee two-step picker.

    Returns dicts of shape:
        {"value": str, "label": str, "kind": str}

    `kind` is one of: "role", "permission", "contextual_requester",
    "contextual_target_person". `value` decodes to working_copy via
    the table in the design spec.
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
    """Build the labeled options for the notification recipients multi-select.

    Returns dicts of shape:
        {"value": str, "label": str, "group": str}

    `value` is the engine string (`requester`, `target_person`, `<role_key>`,
    `permission:<key>`). `group` controls Quasar's option-group rendering.
    """
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
    """Build the labeled options for the notification event select."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor_options.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/frontend/workflow_editor_options.py tests/test_workflow_editor_options.py
git commit -m "feat(workflow-editor): pure-functional option builders + slugifier"
```

---

### Task 2: i18n keys

**Files:**
- Modify: `not_dot_net/frontend/i18n.py` (EN + FR dicts)

- [ ] **Step 1: Confirm a target test exists for i18n parity (so stale FR doesn't slip in)**

```bash
grep -n "validate_translations\|test_i18n" tests/test_i18n.py
```

If a parity test exists, it will fail when EN gains keys without FR. Run it now to confirm baseline:

```bash
uv run pytest tests/test_i18n.py -v
```
Expected: pass.

- [ ] **Step 2: Add the keys to both EN and FR dicts**

Open `not_dot_net/frontend/i18n.py`. Locate the EN dict (the `"en"` block) and append (alphabetize within the section if the file does so; otherwise append at the end before the closing `}`):

```python
        # Workflow editor friendliness
        "wf_label": "Display name",
        "wf_label_help": "Shown to users in the dashboard and request lists.",
        "wf_start_role": "Who can create new requests?",
        "wf_start_role_help": "Anyone with this role sees this workflow on the new-request page.",
        "wf_target_email": "Which field holds the target person's email?",
        "wf_target_email_help": "For workflows about another person (e.g. onboarding) — pick which form field holds their email so we can send them token links.",
        "wf_section_basics": "Basics",
        "wf_section_about_other": "About another person? (advanced)",
        "wf_section_notifications": "Notifications",
        "wf_section_doc_instructions": "Document instructions",
        "step_type_form": "Collect data from the assignee",
        "step_type_approval": "Approval decision (approve / reject)",
        "step_partial_save": "Allow saving as draft",
        "step_corrections_target": "Send back to step",
        "step_assignee": "Who handles this step?",
        "step_actions": "What can the assignee do?",
        "field_display_name": "Display name",
        "field_internal_name": "Internal name",
        "field_internal_name_warn": "Renaming may break workflow references.",
        "field_internal_name_unlock": "Unlock to rename",
        "field_more": "More…",
        "field_options_key": "Pull options from organization list",
        "field_encrypted": "Encrypt at rest (for personal documents)",
        "field_half_width": "Show side-by-side with next field",
        "empty_workflows": "No workflows yet — click Add workflow to create your first one.",
        "empty_steps": "This workflow has no steps yet — click Add step in the panel on the left.",
        "empty_fields": "This step has no fields yet — click Add field below.",
        "empty_notifications": "No notification rules yet — click Add notification rule below.",
        "key_prompt_help": "Lowercase, no spaces. Used in URLs and config — pick something short and stable.",
        "yaml_advanced": "Edit as YAML (advanced)",
        "yaml_back_to_form": "Back to form",
        "event_submit": "When submitted",
        "event_approve": "When approved",
        "event_reject": "When rejected",
        "event_request_corrections": "When changes are requested",
        "event_cancel": "When cancelled",
        "any_step": "Any step",
        "recipient_group_people": "People in this request",
        "recipient_group_roles": "Roles",
        "recipient_group_permissions": "Permissions",
        "recipient_requester": "Requester",
        "recipient_target_person": "Target person",
        "recipient_role_prefix": "Role: ",
        "recipient_permission_prefix": "Permission: ",
        "assignee_kind_role": "Anyone with role",
        "assignee_kind_permission": "Anyone with permission",
        "assignee_kind_requester": "The person who created the request",
        "assignee_kind_target": "The person this request is about",
        "save_dirty_tooltip": "You have unsaved changes",
```

Now mirror in the `"fr"` block (same keys, French translations):

```python
        # Workflow editor friendliness
        "wf_label": "Nom affiché",
        "wf_label_help": "Affiché aux utilisateurs dans le tableau de bord et les listes de demandes.",
        "wf_start_role": "Qui peut créer de nouvelles demandes ?",
        "wf_start_role_help": "Toute personne ayant ce rôle voit ce workflow sur la page de nouvelle demande.",
        "wf_target_email": "Quel champ contient l'email de la personne concernée ?",
        "wf_target_email_help": "Pour les workflows concernant une autre personne (ex. onboarding) — choisissez le champ du formulaire qui contient son email, afin de lui envoyer un lien par token.",
        "wf_section_basics": "Général",
        "wf_section_about_other": "Concerne une autre personne ? (avancé)",
        "wf_section_notifications": "Notifications",
        "wf_section_doc_instructions": "Instructions documentaires",
        "step_type_form": "Collecter des données auprès du responsable",
        "step_type_approval": "Décision d'approbation (approuver / rejeter)",
        "step_partial_save": "Autoriser la sauvegarde en brouillon",
        "step_corrections_target": "Renvoyer à l'étape",
        "step_assignee": "Qui traite cette étape ?",
        "step_actions": "Que peut faire le responsable ?",
        "field_display_name": "Nom affiché",
        "field_internal_name": "Nom interne",
        "field_internal_name_warn": "Le renommage peut casser des références dans le workflow.",
        "field_internal_name_unlock": "Déverrouiller pour renommer",
        "field_more": "Plus…",
        "field_options_key": "Liste d'options issue de l'organisation",
        "field_encrypted": "Chiffrer au repos (pour documents personnels)",
        "field_half_width": "Afficher côte à côte avec le champ suivant",
        "empty_workflows": "Aucun workflow — cliquez sur Ajouter un workflow pour commencer.",
        "empty_steps": "Ce workflow n'a aucune étape — cliquez sur Ajouter une étape dans le panneau de gauche.",
        "empty_fields": "Cette étape n'a aucun champ — cliquez sur Ajouter un champ ci-dessous.",
        "empty_notifications": "Aucune règle de notification — cliquez sur Ajouter une règle ci-dessous.",
        "key_prompt_help": "Minuscules, sans espaces. Utilisé dans les URL et la config — choisissez quelque chose de court et stable.",
        "yaml_advanced": "Éditer en YAML (avancé)",
        "yaml_back_to_form": "Retour au formulaire",
        "event_submit": "Lors de la soumission",
        "event_approve": "Lors de l'approbation",
        "event_reject": "Lors du rejet",
        "event_request_corrections": "Lors d'une demande de corrections",
        "event_cancel": "Lors de l'annulation",
        "any_step": "N'importe quelle étape",
        "recipient_group_people": "Personnes liées à la demande",
        "recipient_group_roles": "Rôles",
        "recipient_group_permissions": "Permissions",
        "recipient_requester": "Demandeur",
        "recipient_target_person": "Personne concernée",
        "recipient_role_prefix": "Rôle : ",
        "recipient_permission_prefix": "Permission : ",
        "assignee_kind_role": "Toute personne ayant le rôle",
        "assignee_kind_permission": "Toute personne ayant la permission",
        "assignee_kind_requester": "La personne qui a créé la demande",
        "assignee_kind_target": "La personne concernée par la demande",
        "save_dirty_tooltip": "Modifications non sauvegardées",
```

- [ ] **Step 3: Run i18n parity tests + full suite**

```bash
uv run pytest tests/test_i18n.py -v
uv run pytest -q
```
Expected: parity test passes (no missing FR keys); full suite still green.

- [ ] **Step 4: Commit**

```bash
git add not_dot_net/frontend/i18n.py
git commit -m "i18n(workflow-editor): friendly labels + help text + section headers (EN/FR)"
```

---

### Task 3: Assignee picker (two-step)

**Files:**
- Modify: `not_dot_net/frontend/workflow_editor.py` (assignee section of `_render_step_editor`; new helpers)
- Modify: `tests/test_workflow_editor.py` (new tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_workflow_editor.py`:

```python
async def test_assignee_picker_writes_role_correctly(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[WorkflowStepConfig(key="s", type="form")]),
    }))
    captured = {}

    @ui.page("/_assignee_role")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_assignee_role")
    dlg = captured["dlg"]
    dlg.set_step_assignee_from_picker("a", "s", "role:admin")
    step = dlg.working_copy.workflows["a"].steps[0]
    assert step.assignee_role == "admin"
    assert step.assignee_permission is None
    assert step.assignee is None


async def test_assignee_picker_writes_contextual_target_person(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[WorkflowStepConfig(key="s", type="form")]),
    }))
    captured = {}

    @ui.page("/_assignee_target")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_assignee_target")
    dlg = captured["dlg"]
    dlg.set_step_assignee_from_picker("a", "s", "contextual:target_person")
    step = dlg.working_copy.workflows["a"].steps[0]
    assert step.assignee == "target_person"
    assert step.assignee_role is None
    assert step.assignee_permission is None


async def test_assignee_picker_writes_permission(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[WorkflowStepConfig(key="s", type="form")]),
    }))
    captured = {}

    @ui.page("/_assignee_perm")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_assignee_perm")
    dlg = captured["dlg"]
    dlg.set_step_assignee_from_picker("a", "s", "permission:approve_workflows")
    step = dlg.working_copy.workflows["a"].steps[0]
    assert step.assignee_permission == "approve_workflows"
    assert step.assignee_role is None
    assert step.assignee is None


async def test_current_assignee_value_for_picker_role():
    """Inverse: given a step, return the value the picker should display."""
    from not_dot_net.frontend.workflow_editor import _current_assignee_value
    from not_dot_net.config import WorkflowStepConfig

    s = WorkflowStepConfig(key="x", type="form", assignee_role="admin")
    assert _current_assignee_value(s) == "role:admin"

    s2 = WorkflowStepConfig(key="x", type="form", assignee_permission="approve_workflows")
    assert _current_assignee_value(s2) == "permission:approve_workflows"

    s3 = WorkflowStepConfig(key="x", type="form", assignee="target_person")
    assert _current_assignee_value(s3) == "contextual:target_person"

    s4 = WorkflowStepConfig(key="x", type="form")
    assert _current_assignee_value(s4) is None
```

- [ ] **Step 2: Run new tests to verify failure**

```bash
uv run pytest tests/test_workflow_editor.py -k "assignee_picker or current_assignee" -v
```
Expected: FAIL — methods/helpers don't exist.

- [ ] **Step 3: Implement helpers and the new dialog method**

Add the import at the top of `not_dot_net/frontend/workflow_editor.py`:

```python
from not_dot_net.backend.permissions import get_permissions
from not_dot_net.backend.roles import roles_config
from not_dot_net.frontend.workflow_editor_options import (
    assignee_options,
    event_options,
    recipient_options,
    _slugify,
)
```

Add a module-level helper:

```python
def _current_assignee_value(step) -> str | None:
    """Map a WorkflowStepConfig's assignee fields back to a picker value."""
    if step.assignee_role:
        return f"role:{step.assignee_role}"
    if step.assignee_permission:
        return f"permission:{step.assignee_permission}"
    if step.assignee:
        return f"contextual:{step.assignee}"
    return None
```

Add this dialog method on `WorkflowEditorDialog`:

```python
    def set_step_assignee_from_picker(self, wf_key: str, step_key: str, value: str | None) -> None:
        """Apply an assignee picker value (e.g. 'role:admin') to the step."""
        step = self._find_step(wf_key, step_key)
        step.assignee_role = None
        step.assignee_permission = None
        step.assignee = None
        if value is None:
            return
        kind, _, raw = value.partition(":")
        if kind == "role":
            step.assignee_role = raw
        elif kind == "permission":
            step.assignee_permission = raw
        elif kind == "contextual":
            step.assignee = raw
        else:
            raise ValueError(f"Unknown assignee picker value: {value}")
```

Cache the option lists once per dialog (so subsequent renders don't re-fetch):

In `__init__`, add:
```python
        self._roles: dict = {}
        self._permissions: dict = {}
```

In `create()`, after fetching `original`, fetch the snapshot:
```python
    @classmethod
    async def create(cls, user) -> "WorkflowEditorDialog":
        original = await workflows_config.get()
        instance = cls(user, original)
        roles_cfg = await roles_config.get()
        instance._roles = dict(roles_cfg.roles)
        instance._permissions = dict(get_permissions())
        instance._build()
        return instance
```

Replace the assignee section of `_render_step_editor` (lines roughly 353-368 in the current file — the `# Assignee — radio group` block through the two `on_value_change` lines). Replace with:

```python
        ui.label(t("step_assignee")).classes("text-subtitle2 q-mt-sm")
        opts = assignee_options(self._roles, self._permissions)
        kinds = [
            ("role", t("assignee_kind_role"), [o for o in opts if o["kind"] == "role"]),
            ("permission", t("assignee_kind_permission"), [o for o in opts if o["kind"] == "permission"]),
            ("contextual_requester", t("assignee_kind_requester"), [o for o in opts if o["kind"] == "contextual_requester"]),
            ("contextual_target_person", t("assignee_kind_target"), [o for o in opts if o["kind"] == "contextual_target_person"]),
        ]
        kind_choices = {k: label for k, label, _ in kinds}

        current_val = _current_assignee_value(step)
        if current_val is None:
            current_kind = "role"
        else:
            for k, _, sub in kinds:
                if any(o["value"] == current_val for o in sub):
                    current_kind = k
                    break
            else:
                current_kind = "role"

        kind_select = ui.select(kind_choices, value=current_kind, label=t("step_assignee")
                                ).classes("w-full").props("dense outlined stack-label")

        sub_opts_by_kind = {k: [{"value": o["value"], "label": o["label"]} for o in sub]
                            for k, _, sub in kinds}
        sub_select_container = ui.row().classes("w-full")
        sub_select_holder: dict = {"select": None}

        def _render_sub_select(kind_value: str) -> None:
            sub_select_container.clear()
            sub_list = sub_opts_by_kind.get(kind_value, [])
            if not sub_list:
                # contextual kinds: no second select; commit immediately
                contextual_value = "contextual:requester" if kind_value == "contextual_requester" else "contextual:target_person"
                self.set_step_assignee_from_picker(wf_key, step.key, contextual_value)
                sub_select_holder["select"] = None
                return
            if len(sub_list) == 1:
                only = sub_list[0]["value"]
                with sub_select_container:
                    ui.label(sub_list[0]["label"]).classes("text-grey")
                self.set_step_assignee_from_picker(wf_key, step.key, only)
                sub_select_holder["select"] = None
                return
            options_dict = {o["value"]: o["label"] for o in sub_list}
            initial = current_val if (current_val and any(o["value"] == current_val for o in sub_list)) else sub_list[0]["value"]
            with sub_select_container:
                sub = ui.select(options_dict, value=initial, label=t("step_assignee")
                                ).classes("w-full").props("dense outlined stack-label")
                sub.on_value_change(lambda e, w=wf_key, k=step.key: self.set_step_assignee_from_picker(w, k, e.value))
            sub_select_holder["select"] = sub
            # Commit the initial value so the picker default is reflected.
            self.set_step_assignee_from_picker(wf_key, step.key, initial)

        _render_sub_select(current_kind)
        kind_select.on_value_change(lambda e, _r=_render_sub_select: _r(e.value))
```

(This block does the rendering work plus initial-state commits so that opening a workflow with no prior assignee writes a sensible default the moment the user picks a kind.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor.py -v
```
Expected: all pass (existing 36+ tests + 4 new).

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat(workflow-editor): two-step assignee picker (no more magic strings)"
```

---

### Task 4: Notification rules table — smart event/step/recipient widgets

**Files:**
- Modify: `not_dot_net/frontend/workflow_editor.py` (`_render_notification_table` + new dialog method)
- Modify: `tests/test_workflow_editor.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_workflow_editor.py`:

```python
async def test_recipient_picker_serializes_permissions(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import NotificationRuleConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[], notifications=[
            NotificationRuleConfig(event="submit", notify=[]),
        ]),
    }))
    captured = {}

    @ui.page("/_recipient1")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_recipient1")
    dlg = captured["dlg"]
    dlg.set_notification_recipients("a", 0, ["permission:approve_workflows", "requester"])
    rule = dlg.working_copy.workflows["a"].notifications[0]
    assert rule.notify == ["permission:approve_workflows", "requester"]


async def test_event_picker_known_values_only(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import NotificationRuleConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[], notifications=[
            NotificationRuleConfig(event="", notify=[]),
        ]),
    }))
    captured = {}

    @ui.page("/_event1")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_event1")
    dlg = captured["dlg"]
    dlg.set_notification_event("a", 0, "approve")
    assert dlg.working_copy.workflows["a"].notifications[0].event == "approve"


async def test_existing_yaml_compat_with_recipient_picker(user: User, admin_user):
    """Loading a config with notify=['permission:foo'] keeps the value verbatim."""
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import NotificationRuleConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[], notifications=[
            NotificationRuleConfig(event="submit", notify=["permission:approve_workflows", "requester"]),
        ]),
    }))
    captured = {}

    @ui.page("/_recipient_compat")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_recipient_compat")
    dlg = captured["dlg"]
    rule = dlg.working_copy.workflows["a"].notifications[0]
    assert rule.notify == ["permission:approve_workflows", "requester"]
    # save round-trip should preserve them
    await dlg.save()
    persisted = await workflows_config.get()
    assert persisted.workflows["a"].notifications[0].notify == ["permission:approve_workflows", "requester"]
```

- [ ] **Step 2: Run new tests to verify failure**

```bash
uv run pytest tests/test_workflow_editor.py -k "recipient or event_picker or yaml_compat" -v
```
Expected: FAIL — `set_notification_recipients` / `set_notification_event` not defined.

- [ ] **Step 3: Implement the new mutators and rewire the table**

Add these methods on `WorkflowEditorDialog`:

```python
    def set_notification_event(self, wf_key: str, index: int, value: str) -> None:
        self.working_copy.workflows[wf_key].notifications[index].event = value

    def set_notification_step(self, wf_key: str, index: int, value: str | None) -> None:
        self.working_copy.workflows[wf_key].notifications[index].step = value

    def set_notification_recipients(self, wf_key: str, index: int, values: list[str]) -> None:
        self.working_copy.workflows[wf_key].notifications[index].notify = list(values)
```

Replace the entire body of `_render_notification_table`:

```python
    def _render_notification_table(self, wf_key: str, wf) -> None:
        step_keys = [s.key for s in wf.steps]
        event_opts = {o["value"]: o["label"] for o in event_options()}

        # Recipient options for this snapshot.
        recip_opts = recipient_options(self._roles, self._permissions)
        recip_value_to_label = {o["value"]: o["label"] for o in recip_opts}
        # Quasar option-group needs a list of dicts with `group` field.
        recip_q_options = [
            {"value": o["value"], "label": o["label"], "group": o["group"]}
            for o in recip_opts
        ]

        if not wf.notifications:
            ui.label(t("empty_notifications")).classes("text-grey text-sm")

        for idx, rule in enumerate(wf.notifications):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.select(
                    options=event_opts,
                    value=rule.event or None,
                    label=t("event_submit").split(" ")[0],  # short header; full help via tooltip
                    on_change=lambda e, i=idx, k=wf_key: self.set_notification_event(k, i, e.value or ""),
                ).props("dense outlined stack-label").classes("w-44")

                step_choices = {None: t("any_step"), **{sk: sk for sk in step_keys}}
                ui.select(
                    options=step_choices,
                    value=rule.step,
                    label="step",
                    on_change=lambda e, i=idx, k=wf_key: self.set_notification_step(k, i, e.value),
                ).props("dense outlined stack-label").classes("w-40")

                # Show "Unknown: <raw>" for any persisted value not in options.
                missing = [v for v in (rule.notify or []) if v not in recip_value_to_label]
                effective_options = list(recip_q_options) + [
                    {"value": v, "label": f"Unknown: {v}", "group": "Unknown"} for v in missing
                ]
                effective_value_to_label = {o["value"]: o["label"] for o in effective_options}

                recip_select = ui.select(
                    options={o["value"]: o["label"] for o in effective_options},
                    value=list(rule.notify or []),
                    multiple=True,
                    label="recipients",
                ).props("dense outlined stack-label use-chips").classes("grow")

                def _bind_recip(w=recip_select, i=idx, k=wf_key):
                    self.set_notification_recipients(k, i, list(w.value or []))
                recip_select.on_value_change(lambda e, _b=_bind_recip: _b())

                ui.button(icon="delete",
                          on_click=lambda i=idx, k=wf_key: self.delete_notification_rule(k, i)
                          ).props("flat dense round color=negative")

        ui.button("+ Add notification rule",
                  on_click=lambda k=wf_key: self.add_notification_rule(k)
                  ).props("flat dense color=primary")
```

(Note: the recipient picker uses a flat `q-select multiple`. Quasar's `option-group` rendering inside `ui.select` is fiddly; for v1 the group label appears in the chip text via the option label itself ("Role: Admin", "Permission: Approve workflows") which is enough to communicate the kind. Re-evaluate group rendering if user feedback says the dropdown needs visual section breaks.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor.py -v
```
Expected: all pass (existing + 3 new).

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat(workflow-editor): smart pickers for notification event/step/recipients"
```

---

### Task 5: Field row simplification — display name + auto-slug + lock-on-save

**Files:**
- Modify: `not_dot_net/frontend/workflow_editor.py` (`__init__`, `set_field_attr`, fields-table render block in `_render_step_editor`, new `unlock_field_name`)
- Modify: `tests/test_workflow_editor.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_workflow_editor.py`:

```python
async def test_field_internal_name_auto_generated_for_new_field(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[WorkflowStepConfig(key="s", type="form")]),
    }))
    captured = {}

    @ui.page("/_field_auto1")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_field_auto1")
    dlg = captured["dlg"]
    dlg.add_field("a", "s")
    dlg.set_field_label_with_autoslug("a", "s", 0, "Email Address")
    field = dlg.working_copy.workflows["a"].steps[0].fields[0]
    assert field.label == "Email Address"
    assert field.name == "email_address"


async def test_field_internal_name_locked_after_save_raises(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import FieldConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[
            WorkflowStepConfig(key="s", type="form", fields=[
                FieldConfig(name="email", type="email", label="Email"),
            ]),
        ]),
    }))
    captured = {}

    @ui.page("/_field_lock1")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_field_lock1")
    dlg = captured["dlg"]
    with pytest.raises(ValueError):
        dlg.set_field_attr("a", "s", 0, "name", "renamed")


async def test_field_internal_name_unlock_allows_rename(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import FieldConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[
            WorkflowStepConfig(key="s", type="form", fields=[
                FieldConfig(name="email", type="email", label="Email"),
            ]),
        ]),
    }))
    captured = {}

    @ui.page("/_field_lock2")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_field_lock2")
    dlg = captured["dlg"]
    dlg.unlock_field_name("a", "s", "email")
    dlg.set_field_attr("a", "s", 0, "name", "renamed")
    assert dlg.working_copy.workflows["a"].steps[0].fields[0].name == "renamed"


async def test_field_label_change_does_not_retype_locked_internal_name(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import FieldConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[
            WorkflowStepConfig(key="s", type="form", fields=[
                FieldConfig(name="email", type="email", label="Email"),
            ]),
        ]),
    }))
    captured = {}

    @ui.page("/_field_lock3")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_field_lock3")
    dlg = captured["dlg"]
    dlg.set_field_label_with_autoslug("a", "s", 0, "Work Email")
    field = dlg.working_copy.workflows["a"].steps[0].fields[0]
    assert field.label == "Work Email"
    assert field.name == "email"  # locked, unchanged
```

- [ ] **Step 2: Run new tests to verify failure**

```bash
uv run pytest tests/test_workflow_editor.py -k "field_auto or field_lock" -v
```
Expected: FAIL — methods don't exist.

- [ ] **Step 3: Implement the lock state, unlock method, and label-with-autoslug helper**

In `__init__` add:

```python
        self._unlocked_fields: set[tuple[str, str, str]] = set()
```

Replace `set_field_attr` to enforce the lock when renaming:

```python
    def set_field_attr(self, wf_key: str, step_key: str, index: int, attr: str, value) -> None:
        step = self._find_step(wf_key, step_key)
        field = step.fields[index]
        if attr == "name" and self._is_field_name_locked(wf_key, step_key, field.name):
            raise ValueError(
                f"Internal name '{field.name}' is locked; call unlock_field_name() first"
            )
        setattr(field, attr, value)
```

Add the helpers:

```python
    def _is_field_saved(self, wf_key: str, step_key: str, field_name: str) -> bool:
        wf = self.original.workflows.get(wf_key)
        if not wf:
            return False
        for step in wf.steps:
            if step.key != step_key:
                continue
            for f in step.fields:
                if f.name == field_name:
                    return True
        return False

    def _is_field_name_locked(self, wf_key: str, step_key: str, field_name: str) -> bool:
        if (wf_key, step_key, field_name) in self._unlocked_fields:
            return False
        return self._is_field_saved(wf_key, step_key, field_name)

    def unlock_field_name(self, wf_key: str, step_key: str, field_name: str) -> None:
        """Unlock a saved field's internal name so it can be renamed."""
        self._unlocked_fields.add((wf_key, step_key, field_name))

    def set_field_label_with_autoslug(self, wf_key: str, step_key: str, index: int, label: str) -> None:
        """Set a field's display name. Auto-generate the internal name when it's
        a new (not-yet-saved) field; leave the internal name alone for saved fields.
        """
        step = self._find_step(wf_key, step_key)
        field = step.fields[index]
        field.label = label
        if self._is_field_name_locked(wf_key, step_key, field.name):
            return
        # New field: regenerate the slug, deduping against sibling names.
        taken = {f.name for j, f in enumerate(step.fields) if j != index and f.name}
        field.name = _slugify(label, taken)
```

Replace the fields-table render block in `_render_step_editor` (the `for idx, field in enumerate(step.fields):` block currently around lines 391-413). Replace with:

```python
        ui.label("Fields").classes("text-subtitle2 q-mt-md")
        if not step.fields:
            ui.label(t("empty_fields")).classes("text-grey text-sm")

        org_keys = [None, *_org_list_field_names()]
        for idx, field in enumerate(step.fields):
            with ui.column().classes("w-full"):
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    ui.input(t("field_display_name"), value=field.label,
                             on_change=lambda e, i=idx, w=wf_key, sk=step.key:
                                 self.set_field_label_with_autoslug(w, sk, i, e.value)
                             ).props("dense outlined stack-label").classes("grow")
                    ui.select(["text", "email", "textarea", "date", "select", "file"],
                              value=field.type, label="type",
                              on_change=lambda e, i=idx, w=wf_key, sk=step.key:
                                  self.set_field_attr(w, sk, i, "type", e.value)
                              ).props("dense outlined stack-label").classes("w-32")
                    ui.switch("Required", value=field.required,
                              on_change=lambda e, i=idx, w=wf_key, sk=step.key:
                                  self.set_field_attr(w, sk, i, "required", e.value))
                    ui.switch(t("field_half_width"), value=field.half_width,
                              on_change=lambda e, i=idx, w=wf_key, sk=step.key:
                                  self.set_field_attr(w, sk, i, "half_width", e.value))
                    with ui.expansion(t("field_more"), icon="more_vert").classes("grow-0"):
                        self._render_field_more(wf_key, step.key, idx, field, org_keys)
                    ui.button(icon="delete",
                              on_click=lambda i=idx, w=wf_key, sk=step.key:
                                  self.delete_field(w, sk, i)
                              ).props("flat dense round color=negative")

        ui.button("+ Add field",
                  on_click=lambda w=wf_key, sk=step.key: self.add_field(w, sk)
                  ).props("flat dense color=primary")
```

Add the new render method (`_render_field_more`):

```python
    def _render_field_more(self, wf_key: str, step_key: str, idx: int, field, org_keys) -> None:
        locked = self._is_field_name_locked(wf_key, step_key, field.name)
        with ui.column().classes("w-full"):
            name_input = ui.input(t("field_internal_name"), value=field.name).props(
                "dense outlined stack-label"
            ).classes("w-full")
            if locked:
                name_input.props("readonly")
                ui.label(t("field_internal_name_warn")).classes("text-warning text-xs")

                def _on_unlock(w=wf_key, sk=step_key, fn=field.name):
                    self.unlock_field_name(w, sk, fn)
                    self._refresh_detail()
                ui.button(t("field_internal_name_unlock"), on_click=_on_unlock
                          ).props("flat dense color=warning")
            else:
                name_input.on_value_change(
                    lambda e, i=idx, w=wf_key, sk=step_key:
                        self._safe_field_rename(w, sk, i, e.value)
                )
            ui.select(org_keys, value=field.options_key, label=t("field_options_key"),
                      on_change=lambda e, i=idx, w=wf_key, sk=step_key:
                          self.set_field_attr(w, sk, i, "options_key", e.value)
                      ).props("dense outlined stack-label").classes("w-full")
            ui.switch(t("field_encrypted"), value=field.encrypted,
                      on_change=lambda e, i=idx, w=wf_key, sk=step_key:
                          self.set_field_attr(w, sk, i, "encrypted", e.value))

    def _safe_field_rename(self, wf_key: str, step_key: str, idx: int, new_name: str) -> None:
        try:
            self.set_field_attr(wf_key, step_key, idx, "name", new_name)
        except ValueError as e:
            ui.notify(str(e), color="negative")
```

(Note on the `Required` label: kept as a literal `"Required"`. If a global `t("required")` key already exists in `i18n.py`, swap to it during implementation.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat(workflow-editor): field display-name w/ auto-slug + lock-on-save"
```

---

### Task 6: Workflow editor right-pane layout — collapsible sections + about-another-person expander

**Files:**
- Modify: `not_dot_net/frontend/workflow_editor.py` (`_render_workflow_editor`)
- Modify: `tests/test_workflow_editor.py` (one structural test)

- [ ] **Step 1: Add a structural test**

Append to `tests/test_workflow_editor.py`:

```python
async def test_workflow_editor_renders_three_sections(user: User, admin_user):
    """The right pane's workflow editor should show three section headers."""
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[]),
    }))

    @ui.page("/_sections")
    async def _page():
        await WorkflowEditorDialog.create(admin_user)

    await user.open("/_sections")
    await user.should_see("Basics")
    await user.should_see("Notifications")
    await user.should_see("Document instructions")
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_workflow_editor.py -k "renders_three_sections" -v
```
Expected: FAIL — section headers not found.

- [ ] **Step 3: Replace `_render_workflow_editor`**

Replace the body of `_render_workflow_editor`:

```python
    def _render_workflow_editor(self, wf_key: str, wf) -> None:
        from not_dot_net.frontend.widgets import keyed_chip_editor

        ui.label(f"Workflow: {wf_key}").classes("text-h6")

        # --- Section 1: Basics (open by default) ---
        with ui.expansion(t("wf_section_basics"), value=True, icon="info").classes("w-full"):
            ui.input(t("wf_label"), value=wf.label,
                     on_change=lambda e, k=wf_key: self.set_workflow_label(k, e.value)
                     ).classes("w-full").props("dense outlined stack-label").tooltip(t("wf_label_help"))

            ui.input(t("wf_start_role"), value=wf.start_role or "",
                     on_change=lambda e, k=wf_key: self.set_workflow_field(k, "start_role", e.value)
                     ).classes("w-full").props("dense outlined stack-label").tooltip(t("wf_start_role_help"))

            with ui.expansion(t("wf_section_about_other"), icon="person_search").classes("w-full"):
                field_names = sorted({f.name for s in wf.steps for f in s.fields if f.name})
                if field_names:
                    options = {None: "(none)", **{n: n for n in field_names}}
                    ui.select(options, value=wf.target_email_field,
                              label=t("wf_target_email"),
                              on_change=lambda e, k=wf_key: self.set_workflow_field(k, "target_email_field", e.value or None)
                              ).classes("w-full").props("dense outlined stack-label").tooltip(t("wf_target_email_help"))
                else:
                    ui.input(t("wf_target_email"), value=wf.target_email_field or "",
                             on_change=lambda e, k=wf_key: self.set_workflow_field(k, "target_email_field", e.value or None)
                             ).classes("w-full").props("dense outlined stack-label").tooltip(t("wf_target_email_help"))

        # --- Section 2: Notifications (collapsed; show count) ---
        n_notif = len(wf.notifications)
        with ui.expansion(f"{t('wf_section_notifications')}  ({n_notif})", icon="notifications"
                          ).classes("w-full"):
            self._render_notification_table(wf_key, wf)

        # --- Section 3: Document instructions (collapsed; show count) ---
        n_di = len(wf.document_instructions or {})
        with ui.expansion(f"{t('wf_section_doc_instructions')}  ({n_di})", icon="description"
                          ).classes("w-full"):
            di = keyed_chip_editor(wf.document_instructions or {}, key_label="status")
            self._workflow_doc_instructions_widget = (wf_key, di)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat(workflow-editor): collapsible sections + target-email-field expander"
```

---

### Task 7: YAML reposition — replace tabs with header `</>` button

**Files:**
- Modify: `not_dot_net/frontend/workflow_editor.py` (`_build`, new `_open_yaml_view` / `_close_yaml_view`)
- Modify: `tests/test_workflow_editor.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_workflow_editor.py`:

```python
async def test_yaml_button_swaps_body(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[]),
    }))
    captured = {}

    @ui.page("/_yaml_swap")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_yaml_swap")
    dlg = captured["dlg"]
    assert dlg._active_tab == "Form"
    dlg._open_yaml_view()
    assert dlg._active_tab == "YAML"
    assert dlg._yaml_editor is not None
    assert "label: A" in dlg._yaml_editor.value
    dlg._close_yaml_view()
    assert dlg._active_tab == "Form"
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_workflow_editor.py -k "yaml_button_swaps" -v
```
Expected: FAIL — `_open_yaml_view` not defined.

- [ ] **Step 3: Replace the tab structure with body-swap**

Replace `_build`:

```python
    def _build(self) -> None:
        self.dialog = ui.dialog().props("maximized")
        with self.dialog, ui.card().classes("w-full h-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("workflows_editor")).classes("text-h6")
                ui.button(icon="code", on_click=self._open_yaml_view
                          ).props("flat dense").tooltip(t("yaml_advanced"))
            self._body_container = ui.column().classes("w-full grow")
            with ui.row().classes("w-full justify-between items-center"):
                self._warnings_label = ui.label("").classes("text-warning text-sm")
                self._warnings_label.on("click", lambda e: self._show_warnings(self._current_warnings))
                with ui.row():
                    ui.button(t("cancel"), on_click=self._on_cancel_click).props("flat")
                    ui.button(t("reset_defaults"), on_click=self.reset).props("flat color=grey")
                    self._save_button = ui.button(t("save"), on_click=self.save).props("color=primary")
        self._render_form_body()
```

Add `__init__` field `self._body_container = None` and `self._save_button = None`.

Add the new methods and refactor body rendering:

```python
    def _render_form_body(self) -> None:
        self._active_tab = "Form"
        self._body_container.clear()
        with self._body_container:
            with ui.row().classes("w-full grow no-wrap"):
                self._tree_container = ui.column().classes("w-72 q-pr-md").style("border-right: 1px solid #e0e0e0")
                self._detail_container = ui.column().classes("grow")
        self._refresh_tree()
        self._refresh_detail()

    def _open_yaml_view(self) -> None:
        # Capture form-side state into the model before rendering YAML.
        self._collect_widget_state()
        self._active_tab = "YAML"
        self._body_container.clear()
        with self._body_container:
            with ui.row().classes("w-full justify-between items-center"):
                ui.button(t("yaml_back_to_form"), icon="arrow_back",
                          on_click=self._close_yaml_view).props("flat")
            self._yaml_editor = ui.codemirror(self.dump_yaml(), language="yaml"
                                              ).classes("w-full").style("min-height: 400px")

    def _close_yaml_view(self) -> None:
        if self._yaml_editor is not None:
            try:
                self.apply_yaml(self._yaml_editor.value)
            except ValueError as err:
                ui.notify(f"Invalid YAML: {err}", color="negative", multi_line=True)
                return  # stay on YAML so user can fix
        self._yaml_editor = None
        self._render_form_body()
```

Remove the now-defunct `_on_tab_change` method and the `ui.tabs()` block.

(The existing `save()` method already checks `_active_tab == "YAML"` to apply pending YAML — it continues to work.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/frontend/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat(workflow-editor): hide YAML behind </> button instead of co-equal tab"
```

---

### Task 8: Dirty indicator + unknown-recipient warning + final smoke

**Files:**
- Modify: `not_dot_net/frontend/workflow_editor.py` (`_refresh_detail` adds save-button badge; `compute_warnings` gets the new check)
- Modify: `tests/test_workflow_editor.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_workflow_editor.py`:

```python
async def test_unknown_recipient_warning(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    from not_dot_net.config import NotificationRuleConfig
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[], notifications=[
            NotificationRuleConfig(event="submit", notify=["nonexistent_role", "permission:made_up"]),
        ]),
    }))
    captured = {}

    @ui.page("/_unknown_recip")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_unknown_recip")
    dlg = captured["dlg"]
    warnings = dlg.compute_warnings()
    assert any("nonexistent_role" in w for w in warnings)
    assert any("permission:made_up" in w for w in warnings)


async def test_dirty_indicator_visible_after_edit(user: User, admin_user):
    from not_dot_net.frontend.workflow_editor import WorkflowEditorDialog
    await workflows_config.set(WorkflowsConfig(workflows={
        "a": WorkflowConfig(label="A", steps=[]),
    }))
    captured = {}

    @ui.page("/_dirty_badge")
    async def _page():
        captured["dlg"] = await WorkflowEditorDialog.create(admin_user)

    await user.open("/_dirty_badge")
    dlg = captured["dlg"]
    # Pre-edit: no badge content
    assert dlg._save_dirty_badge is None or not dlg._save_dirty_badge.visible
    dlg.set_workflow_label("a", "Edited")
    dlg._update_save_dirty_indicator()
    assert dlg._save_dirty_badge is not None
    assert dlg._save_dirty_badge.visible
```

- [ ] **Step 2: Run new tests to verify failure**

```bash
uv run pytest tests/test_workflow_editor.py -k "unknown_recipient or dirty_indicator_visible" -v
```
Expected: FAIL — features don't exist.

- [ ] **Step 3: Implement the unknown-recipient warning + dirty badge**

Add to `compute_warnings()`, after the existing `for nr in wf.notifications:` loop body's `if nr.step` check, append:

```python
                # Unknown recipients (not in current roles or permission registry).
                known_recip_values = {o["value"] for o in recipient_options(self._roles, self._permissions)}
                for v in (nr.notify or []):
                    if v not in known_recip_values:
                        warnings.append(
                            f"[{wf_key}] notification recipient '{v}' not found in current roles or permissions"
                        )
```

Add to `__init__`:

```python
        self._save_dirty_badge = None
```

Modify `_build` to attach a badge slot to the save button. After the line creating `self._save_button`, add:

```python
                    with self._save_button:
                        self._save_dirty_badge = ui.badge(color="warning", text_color="white"
                                                          ).props("floating rounded")
                        self._save_dirty_badge.text = "•"
                        self._save_dirty_badge.tooltip(t("save_dirty_tooltip"))
                        self._save_dirty_badge.visible = False
```

Add the helper method:

```python
    def _update_save_dirty_indicator(self) -> None:
        if self._save_dirty_badge is None:
            return
        self._save_dirty_badge.visible = self.is_dirty()
```

Call `self._update_save_dirty_indicator()` at the end of `_refresh_detail()` (next to the warnings refresh).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_workflow_editor.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```
Expected: full suite green.

- [ ] **Step 6: Manual smoke test**

Start the dev server:

```bash
uv run python -m not_dot_net.cli serve --host localhost --port 8088
```

In a browser as admin:

1. Settings → Workflows → "Edit workflows…". Confirm the dialog opens with the new sections (Basics open, Notifications + Document instructions collapsed) and no Form/YAML tabs at the top.
2. Click the `</>` icon in the header. The body swaps to the YAML editor with a "← Back to form" button. Click it; the body returns to the form.
3. Select an existing step. The "Who handles this step?" picker shows two dropdowns (kind + value). Pick "The person this request is about" — confirm the value dropdown disappears and the working state is contextual.
4. Open the Notifications section. Each rule row shows: friendly event labels ("When approved" etc.), a step picker with "Any step" as the empty value, and a recipient multi-select with chips like "Role: Admin", "Permission: Approve workflows", "Requester".
5. Add a new field to a step. Type "Email Address" in Display name → confirm the More… expander shows internal name "email_address" populated automatically.
6. Open an existing field's More… → confirm the internal name is readonly with a warning and an "Unlock to rename" button.
7. Make any edit → confirm the orange dot appears on the Save button. Save. Reopen the dialog → confirm the change persisted.
8. Toggle a workflow's notification rule's recipients to include a non-existent role (via YAML tab, then come back). Confirm the warnings pill shows the unknown-recipient warning.

If anything is off, fix and re-run the test suite.

- [ ] **Step 7: Commit**

```bash
git add not_dot_net/frontend/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat(workflow-editor): unknown-recipient warning + save dirty indicator"
```

---

## Self-review checklist (for the engineer)

After all tasks pass:

1. `uv run pytest` — full suite green.
2. Read `not_dot_net/frontend/workflow_editor.py` end to end. The file may be ~750 lines after this work; if any single method exceeds ~120 lines (especially `_render_step_editor`), consider extracting helpers but do NOT refactor for the sake of it.
3. Manually exercise scenarios 1-8 above one more time.
4. Confirm the YAML escape hatch still works as a safety valve: pasting an old config (with `assignee_role: staff` and `notify: [permission:approve_workflows]`) round-trips through Form → save → reload → Form with the right pre-selected picker values.
5. Update the project memory `MEMORY.md` if any new gotcha emerged during execution that's worth saving.
