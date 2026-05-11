# Workflow Dashboard & UI Implementation Plan (Part 3: Frontend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the NiceGUI frontend for the workflow engine: dashboard (my requests + awaiting action), new request flow, step renderer (form/approval), token page, and updated shell with role-based tab visibility.

**Architecture:** `shell.py` is the layout with role-based tabs. `dashboard.py` shows cards for owned and actionable requests. `new_request.py` lists startable workflow types and renders the first step. `workflow_step.py` is a reusable component that renders form fields or approval UI. `workflow_token.py` is a standalone page for external token access.

**Tech Stack:** NiceGUI (Quasar/Vue), existing `workflow_service.py` for data, `i18n.py` for translations.

**Spec:** `docs/superpowers/specs/2026-03-22-workflow-engine-design.md` — Section 7

---

### Task 1: i18n Keys for Workflow UI

**Files:**
- Modify: `not_dot_net/frontend/i18n.py`

- [ ] **Step 1: Add workflow translation keys**

Add the following keys to both `en` and `fr` dicts in `TRANSLATIONS`:

```python
# In "en" dict, after the "# Common" section:
        # Workflow
        "dashboard": "Dashboard",
        "new_request": "New Request",
        "my_requests": "My Requests",
        "awaiting_action": "Awaiting My Action",
        "no_requests": "No requests yet",
        "no_pending": "Nothing pending",
        "workflow_type": "Type",
        "current_step": "Current Step",
        "created_by": "Created by",
        "created_at": "Created",
        "approve": "Approve",
        "reject": "Reject",
        "approved": "Approved",
        "rejected": "Rejected",
        "completed": "Completed",
        "in_progress": "In Progress",
        "comment": "Comment (optional)",
        "select_workflow": "Select a workflow to start",
        "request_created": "Request created",
        "step_submitted": "Step submitted",
        "draft_saved": "Draft saved",
        "required_field": "This field is required",
        "token_expired": "This link has expired or is invalid",
        "token_welcome": "Please complete the form below",
        "save_draft": "Save Draft",
        "file_upload": "Upload File",
        "target_person": "Target Person",

# In "fr" dict:
        # Workflow
        "dashboard": "Tableau de bord",
        "new_request": "Nouvelle demande",
        "my_requests": "Mes demandes",
        "awaiting_action": "En attente de mon action",
        "no_requests": "Aucune demande",
        "no_pending": "Rien en attente",
        "workflow_type": "Type",
        "current_step": "Étape en cours",
        "created_by": "Créé par",
        "created_at": "Créé le",
        "approve": "Approuver",
        "reject": "Rejeter",
        "approved": "Approuvé",
        "rejected": "Rejeté",
        "completed": "Terminé",
        "in_progress": "En cours",
        "comment": "Commentaire (optionnel)",
        "select_workflow": "Sélectionnez un workflow à lancer",
        "request_created": "Demande créée",
        "step_submitted": "Étape envoyée",
        "draft_saved": "Brouillon enregistré",
        "required_field": "Ce champ est obligatoire",
        "token_expired": "Ce lien a expiré ou est invalide",
        "token_welcome": "Veuillez remplir le formulaire ci-dessous",
        "save_draft": "Enregistrer le brouillon",
        "file_upload": "Téléverser un fichier",
        "target_person": "Personne concernée",
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/i18n.py
git commit -m "feat: add workflow UI translation keys"
```

---

### Task 2: Workflow Step Renderer

**Files:**
- Create: `not_dot_net/frontend/workflow_step.py`

This is the reusable component for rendering a form or approval step. Used by dashboard, new_request, and token page.

- [ ] **Step 1: Create workflow_step.py**

```python
# not_dot_net/frontend/workflow_step.py
"""Reusable step renderer — form fields or approval UI."""

from nicegui import ui

from not_dot_net.backend.workflow_engine import get_completion_status
from not_dot_net.config import WorkflowStepConfig
from not_dot_net.frontend.i18n import t


def render_step_form(
    step: WorkflowStepConfig,
    data: dict,
    on_submit,
    on_save_draft=None,
    files: dict | None = None,
    on_file_upload=None,
):
    """Render a form step's fields. Returns dict of field name -> ui element."""
    fields = {}
    for field_cfg in step.fields:
        label = field_cfg.label or field_cfg.name
        value = data.get(field_cfg.name, "")

        if field_cfg.type == "textarea":
            fields[field_cfg.name] = ui.textarea(
                label=label, value=value
            ).props("outlined dense").classes("w-full")
        elif field_cfg.type == "date":
            with ui.input(label=label, value=value).props("outlined dense") as inp:
                with ui.menu().props("no-parent-event") as menu:
                    with ui.date(on_change=lambda e, i=inp, m=menu: _set_date(i, m, e)):
                        pass
                with inp.add_slot("append"):
                    ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
            fields[field_cfg.name] = inp
        elif field_cfg.type == "select":
            options = _resolve_options(field_cfg.options_key)
            fields[field_cfg.name] = ui.select(
                label=label, options=options, value=value or None
            ).props("outlined dense").classes("w-full")
        elif field_cfg.type == "file":
            uploaded = (files or {}).get(field_cfg.name)
            if uploaded:
                ui.label(f"{label}: uploaded").classes("text-positive text-sm")
            else:
                with ui.row().classes("items-center gap-2"):
                    ui.label(label).classes("text-sm")
                    if on_file_upload:
                        ui.upload(
                            label=t("file_upload"),
                            auto_upload=True,
                            on_upload=lambda e, name=field_cfg.name: on_file_upload(name, e),
                        ).props("dense flat").classes("max-w-xs")
            fields[field_cfg.name] = None  # files tracked separately
        elif field_cfg.type == "email":
            fields[field_cfg.name] = ui.input(
                label=label, value=value, validation={"Invalid email": lambda v: "@" in v if v else True}
            ).props("outlined dense type=email").classes("w-full")
        else:
            fields[field_cfg.name] = ui.input(
                label=label, value=value
            ).props("outlined dense").classes("w-full")

    # Completion status for partial-save steps
    if step.partial_save:
        _render_completion_indicator(step, data, files or {})

    with ui.row().classes("mt-4 gap-2"):
        if on_save_draft and step.partial_save:
            ui.button(t("save_draft"), on_click=lambda: on_save_draft(_collect_data(fields))).props(
                "flat"
            )

        async def validated_submit():
            collected = _collect_data(fields)
            missing = [
                f.label or f.name for f in step.fields
                if f.required and f.type != "file" and not collected.get(f.name)
            ]
            if missing:
                ui.notify(f"{t('required_field')}: {', '.join(missing)}", color="negative")
                return
            await on_submit(collected)

        ui.button(t("submit"), on_click=validated_submit).props("color=primary")

    return fields


def _render_completion_indicator(step: WorkflowStepConfig, data: dict, files: dict):
    """Show which required fields are filled for partial-save steps."""
    required = [f for f in step.fields if f.required]
    if not required:
        return
    filled = sum(
        1 for f in required
        if (f.type == "file" and files.get(f.name)) or (f.type != "file" and data.get(f.name))
    )
    ui.linear_progress(value=filled / len(required)).classes("w-full mb-2")
    ui.label(f"{filled}/{len(required)}").classes("text-sm text-grey")


def render_approval(
    request_data: dict,
    workflow: WorkflowConfig,
    step: WorkflowStepConfig,
    on_approve,
    on_reject,
):
    """Render approval view: read-only data + approve/reject."""
    ui.label(workflow.label).classes("text-h6")

    for key, value in request_data.items():
        if value:
            ui.label(f"{key}: {value}").classes("text-sm")

    comment_input = ui.textarea(label=t("comment")).props("outlined dense").classes("w-full mt-2")

    with ui.row().classes("mt-4 gap-2"):
        ui.button(
            t("approve"),
            icon="check",
            on_click=lambda: on_approve(comment_input.value),
        ).props("color=positive")
        ui.button(
            t("reject"),
            icon="close",
            on_click=lambda: on_reject(comment_input.value),
        ).props("color=negative")


def render_status_badge(status: str):
    """Render a colored status badge."""
    colors = {
        "in_progress": "blue",
        "completed": "positive",
        "rejected": "negative",
    }
    color = colors.get(status, "grey")
    ui.badge(t(status), color=color)


def _collect_data(fields: dict) -> dict:
    """Collect values from UI fields."""
    return {
        name: (el.value if el is not None else None)
        for name, el in fields.items()
        if el is not None
    }


def _set_date(inp, menu, event):
    inp.value = event.value
    menu.close()


def _resolve_options(options_key: str | None) -> list[str]:
    """Resolve select field options from config."""
    if not options_key:
        return []
    from not_dot_net.config import get_settings
    settings = get_settings()
    if options_key == "teams":
        return settings.teams
    if options_key == "roles":
        from not_dot_net.backend.roles import Role
        return [r.value for r in Role]
    return []
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass (no new tests for UI component — tested via integration)

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/workflow_step.py
git commit -m "feat: add reusable workflow step renderer component"
```

---

### Task 3: Dashboard Page

**Files:**
- Create: `not_dot_net/frontend/dashboard.py`
- Modify: `not_dot_net/backend/workflow_service.py` (add `list_events` and `list_all_requests`)

- [ ] **Step 1: Add `list_events` and `list_all_requests` to workflow_service.py**

Add these two functions after `list_actionable`:

```python
async def list_events(request_id: uuid.UUID) -> list[WorkflowEvent]:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowEvent)
            .where(WorkflowEvent.request_id == request_id)
            .order_by(WorkflowEvent.created_at.asc())
        )
        return list(result.scalars().all())


async def list_all_requests() -> list[WorkflowRequest]:
    """Admin-only: list all requests."""
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRequest)
            .order_by(WorkflowRequest.created_at.desc())
        )
        return list(result.scalars().all())
```

- [ ] **Step 2: Create dashboard.py**

```python
# not_dot_net/frontend/dashboard.py
"""Dashboard tab — My Requests + Awaiting My Action."""

from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.roles import Role, has_role
from not_dot_net.backend.workflow_service import (
    list_user_requests,
    list_all_requests,
    list_actionable,
    list_events,
    submit_step,
)
from not_dot_net.backend.workflow_engine import get_current_step_config
from not_dot_net.config import get_settings
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import (
    render_approval,
    render_step_form,
    render_status_badge,
)


def render(user: User):
    """Render the dashboard tab content."""
    my_requests_container = ui.column().classes("w-full")
    actionable_container = ui.column().classes("w-full")

    async def refresh():
        await _render_my_requests(my_requests_container, user)
        await _render_actionable(actionable_container, user)

    ui.timer(0, refresh, once=True)


async def _render_my_requests(container, user: User):
    container.clear()
    # Admin sees all requests, others see only their own
    if has_role(user, Role.ADMIN):
        requests = await list_all_requests()
    else:
        requests = await list_user_requests(user.id)

    with container:
        ui.label(t("my_requests")).classes("text-h6 mb-2")
        if not requests:
            ui.label(t("no_requests")).classes("text-grey")
            return

        settings = get_settings()
        state = {"expanded_id": None}

        for req in requests:
            wf = settings.workflows.get(req.type)
            label = wf.label if wf else req.type
            step_config = get_current_step_config(req, wf) if wf else None
            step_label = step_config.key if step_config else req.current_step

            with ui.card().classes("w-full cursor-pointer") as card:
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.column().classes("gap-0"):
                        ui.label(label).classes("font-bold")
                        if req.target_email:
                            ui.label(f"{t('target_person')}: {req.target_email}").classes(
                                "text-sm text-grey"
                            )
                        ui.label(f"{t('current_step')}: {step_label}").classes("text-sm")
                    render_status_badge(req.status)

                detail_container = ui.column().classes("w-full mt-2")
                detail_container.set_visibility(False)

                async def toggle_expand(dc=detail_container, r=req, st=state):
                    if st["expanded_id"] == r.id:
                        dc.set_visibility(False)
                        st["expanded_id"] = None
                    else:
                        st["expanded_id"] = r.id
                        dc.set_visibility(True)
                        dc.clear()
                        with dc:
                            ui.separator()
                            events = await list_events(r.id)
                            for ev in events:
                                ts = ev.created_at.strftime("%Y-%m-%d %H:%M") if ev.created_at else ""
                                ui.label(f"{ts} — {ev.step_key}: {ev.action}").classes("text-sm")
                                if ev.comment:
                                    ui.label(f"  {ev.comment}").classes("text-sm text-grey ml-4")

                card.on("click", toggle_expand)


async def _render_actionable(container, user: User):
    container.clear()
    requests = await list_actionable(user)

    with container:
        ui.label(t("awaiting_action")).classes("text-h6 mb-2 mt-4")
        if not requests:
            ui.label(t("no_pending")).classes("text-grey")
            return

        settings = get_settings()
        for req in requests:
            wf = settings.workflows.get(req.type)
            if not wf:
                continue
            step_config = get_current_step_config(req, wf)
            if not step_config:
                continue

            with ui.card().classes("w-full") as card:
                with ui.row().classes("items-center justify-between w-full"):
                    with ui.column().classes("gap-0"):
                        ui.label(wf.label).classes("font-bold")
                        ui.label(f"{t('current_step')}: {step_config.key}").classes("text-sm")
                        if req.target_email:
                            ui.label(f"{t('target_person')}: {req.target_email}").classes(
                                "text-sm text-grey"
                            )
                    if req.updated_at:
                        ui.label(req.updated_at.strftime("%Y-%m-%d")).classes("text-sm text-grey")

                action_container = ui.column().classes("w-full")

                async def handle_approve(comment, r=req):
                    try:
                        await submit_step(r.id, user.id, "approve", comment=comment)
                        ui.notify(t("step_submitted"), color="positive")
                        await _render_actionable(container, user)
                    except Exception as e:
                        ui.notify(str(e), color="negative")

                async def handle_reject(comment, r=req):
                    try:
                        await submit_step(r.id, user.id, "reject", comment=comment)
                        ui.notify(t("step_submitted"), color="positive")
                        await _render_actionable(container, user)
                    except Exception as e:
                        ui.notify(str(e), color="negative")

                async def handle_submit(data, r=req):
                    try:
                        await submit_step(r.id, user.id, "submit", data=data)
                        ui.notify(t("step_submitted"), color="positive")
                        await _render_actionable(container, user)
                    except Exception as e:
                        ui.notify(str(e), color="negative")

                with action_container:
                    if step_config.type == "approval":
                        render_approval(req.data, wf, step_config, handle_approve, handle_reject)
                    elif step_config.type == "form":
                        render_step_form(step_config, req.data, on_submit=handle_submit)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/backend/workflow_service.py not_dot_net/frontend/dashboard.py
git commit -m "feat: add workflow dashboard with my requests and action queue"
```

---

### Task 4: New Request Page

**Files:**
- Create: `not_dot_net/frontend/new_request.py`

- [ ] **Step 1: Create new_request.py**

```python
# not_dot_net/frontend/new_request.py
"""New Request tab — pick a workflow type and fill the first step."""

from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.roles import Role, has_role
from not_dot_net.backend.workflow_service import create_request
from not_dot_net.config import get_settings
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import render_step_form


def render(user: User):
    """Render the new request tab content."""
    settings = get_settings()
    container = ui.column().classes("w-full")

    with container:
        ui.label(t("select_workflow")).classes("text-h6 mb-4")

        for wf_key, wf_config in settings.workflows.items():
            if not has_role(user, Role(wf_config.start_role)):
                continue

            with ui.card().classes("w-full cursor-pointer") as card:
                ui.label(wf_config.label).classes("font-bold")

                form_container = ui.column().classes("w-full mt-2")
                form_container.set_visibility(False)

                first_step = wf_config.steps[0]

                async def handle_submit(data, key=wf_key, fc=form_container):
                    await create_request(
                        workflow_type=key,
                        created_by=user.id,
                        data=data,
                    )
                    ui.notify(t("request_created"), color="positive")
                    fc.set_visibility(False)

                def toggle_form(fc=form_container, step=first_step):
                    visible = not fc.visible
                    fc.set_visibility(visible)
                    if visible:
                        fc.clear()
                        with fc:
                            render_step_form(step, {}, on_submit=handle_submit)

                card.on("click", toggle_form)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/new_request.py
git commit -m "feat: add new request page with workflow type picker"
```

---

### Task 5: Token Page

**Files:**
- Modify: `not_dot_net/backend/workflow_service.py` (make `actor_id` optional in `submit_step`)
- Create: `not_dot_net/frontend/workflow_token.py`

- [ ] **Step 1: Make actor_id optional in submit_step**

In `workflow_service.py`, change the `submit_step` signature:
```python
async def submit_step(
    request_id: uuid.UUID,
    actor_id: uuid.UUID | None,  # was: uuid.UUID
    action: str,
    ...
```

This allows token-based access where there's no authenticated user.

- [ ] **Step 2: Create workflow_token.py**

```python
# not_dot_net/frontend/workflow_token.py
"""Standalone token page — no login required."""

from nicegui import ui

from not_dot_net.backend.workflow_service import (
    get_request_by_token,
    save_draft,
    submit_step,
)
from not_dot_net.backend.workflow_engine import get_current_step_config
from not_dot_net.config import get_settings
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import render_step_form


def setup():
    @ui.page("/workflow/token/{token}")
    async def token_page(token: str):
        req = await get_request_by_token(token)

        if req is None:
            with ui.column().classes("absolute-center items-center"):
                ui.icon("error", size="xl", color="negative")
                ui.label(t("token_expired")).classes("text-h6")
            return

        settings = get_settings()
        wf = settings.workflows.get(req.type)
        if not wf:
            ui.label(t("token_expired"))
            return

        step_config = get_current_step_config(req, wf)
        if not step_config:
            ui.label(t("token_expired"))
            return

        with ui.column().classes("max-w-2xl mx-auto p-6"):
            ui.label(wf.label).classes("text-h5 mb-2")
            ui.label(t("token_welcome")).classes("text-grey mb-4")

            form_container = ui.column().classes("w-full")

            async def handle_submit(data):
                await submit_step(
                    req.id, actor_id=None, action="submit", data=data,
                )
                form_container.clear()
                with form_container:
                    ui.icon("check_circle", size="xl", color="positive")
                    ui.label(t("step_submitted")).classes("text-h6")

            async def handle_save_draft(data):
                await save_draft(
                    req.id, data=data, actor_token=token,
                )
                ui.notify(t("draft_saved"), color="positive")

            with form_container:
                render_step_form(
                    step_config,
                    req.data,
                    on_submit=handle_submit,
                    on_save_draft=handle_save_draft if step_config.partial_save else None,
                )
```

- [ ] **Step 3: Modify `not_dot_net/app.py` to register the token page**

Add import and setup call:

```python
# After: from not_dot_net.frontend.shell import setup as setup_shell
from not_dot_net.frontend.workflow_token import setup as setup_token

# After: setup_shell()
    setup_token()
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/workflow_service.py not_dot_net/frontend/workflow_token.py not_dot_net/app.py
git commit -m "feat: add standalone token page for external workflow access"
```

---

### Task 6: Update Shell with Role-Based Tabs

**Files:**
- Modify: `not_dot_net/frontend/shell.py`

- [ ] **Step 1: Rewrite shell.py with role-based tabs**

Replace the entire `main_page` function body in `setup()` to add Dashboard and New Request tabs with role-based visibility:

```python
# not_dot_net/frontend/shell.py
from typing import Optional

from fastapi import Depends
from fastapi.responses import RedirectResponse
from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.roles import Role, has_role
from not_dot_net.backend.users import current_active_user_optional
from not_dot_net.frontend.directory import render as render_directory
from not_dot_net.frontend.dashboard import render as render_dashboard
from not_dot_net.frontend.new_request import render as render_new_request
from not_dot_net.frontend.i18n import SUPPORTED_LOCALES, get_locale, set_locale, t


def setup():
    @ui.page("/")
    def main_page(
        user: Optional[User] = Depends(current_active_user_optional),
    ) -> Optional[RedirectResponse]:
        if not user:
            return RedirectResponse("/login")

        locale = get_locale()
        people_label = t("people")
        dashboard_label = t("dashboard")
        new_request_label = t("new_request")

        can_create = has_role(user, Role.STAFF)

        with ui.header().classes("row items-center justify-between px-4"):
            ui.label(t("app_name")).classes("text-h6 text-white")
            with ui.tabs().classes("ml-4") as tabs:
                ui.tab(dashboard_label, icon="dashboard")
                ui.tab(people_label, icon="people")
                if can_create:
                    ui.tab(new_request_label, icon="add_circle")
            with ui.row().classes("items-center"):
                def on_lang_change(e):
                    set_locale(e.value)
                    ui.run_javascript("window.location.reload()")

                ui.toggle(
                    list(SUPPORTED_LOCALES), value=locale, on_change=on_lang_change
                ).props("flat dense color=white text-color=white toggle-color=white")

                with ui.button(icon="person").props("flat color=white"):
                    with ui.menu():
                        ui.menu_item(t("my_profile"), on_click=lambda: tabs.set_value(people_label))
                        ui.menu_item(t("logout"), on_click=lambda: _logout())

        with ui.tab_panels(tabs, value=dashboard_label).classes("w-full"):
            with ui.tab_panel(dashboard_label):
                render_dashboard(user)
            with ui.tab_panel(people_label):
                render_directory(user)
            if can_create:
                with ui.tab_panel(new_request_label):
                    render_new_request(user)

        return None


def _logout():
    ui.run_javascript(
        'document.cookie = "fastapiusersauth=; path=/; max-age=0";'
        'window.location.href = "/login";'
    )
```

**Key changes from original:**
- Dashboard tab is the default (first tab, default value)
- New Request tab only visible if user has `staff` or higher role
- Onboarding tab removed (was already removed in Plan 1)
- `_go_to_profile` simplified to just switch to people tab
- Imports added for `dashboard`, `new_request`, `roles`

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/shell.py
git commit -m "feat: update shell with role-based dashboard and new request tabs"
```

---

## What's Next

After Plan 3, the workflow engine feature branch is complete:
- Backend: roles, config, models, engine, service, mail, notifications
- Frontend: dashboard, new request, step renderer, token page, shell

Use `superpowers:finishing-a-development-branch` to merge/PR the `feature/workflow-engine` branch.
