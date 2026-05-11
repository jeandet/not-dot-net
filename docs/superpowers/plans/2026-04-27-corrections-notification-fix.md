# Corrections Notification & Resend Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken request_corrections flow (newcomer not notified with working link) and add a "resend notification" button for the admin team.

**Architecture:** Three fixes: (1) Include the new token link in the `request_corrections` notification email, (2) expose a `resend_notification` service function that regenerates the token and fires the notification, (3) add a "Resend Notification" button on the workflow detail page for users who can act on the current step.

**Tech Stack:** NiceGUI, async SMTP notifications, existing workflow service + engine

---

## Root Cause Analysis

When admin clicks "Request Corrections" on `admin_validation` step:
1. `compute_next_step()` returns `("newcomer_info", IN_PROGRESS)` — correct
2. `submit_step()` clears the old token (line 363), then generates a new one (line 374) because `newcomer_info.assignee == "target_person"` — correct
3. `_fire_notifications()` fires with `event="request_corrections"` — correct
4. **Bug**: `notify()` only substitutes the token_link template when `event == "submit"` (line 128). For `request_corrections`, it uses the `request_corrections` template which says "visit the link you received previously" — but that link is dead (old token cleared, new token generated).

**Fix**: In `notify()`, also send the `token_link` template (or include the link in the corrections template) when `request.token` exists and the event is `request_corrections`.

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `not_dot_net/backend/notifications.py` | Include token link for request_corrections events |
| Modify | `not_dot_net/backend/workflow_service.py` | Add `resend_notification()` service function |
| Modify | `not_dot_net/frontend/workflow_detail.py` | Add "Resend Notification" button |
| Modify | `not_dot_net/frontend/i18n.py` | i18n keys for resend button |
| Modify | `tests/test_notifications.py` | Test corrections notification includes link |
| Create | `tests/test_resend_notification.py` | Test resend_notification service function |

---

### Task 1: Fix request_corrections notification to include token link

**Files:**
- Modify: `not_dot_net/backend/notifications.py`
- Modify: `tests/test_notifications.py`

- [ ] **Step 1: Write failing test**

Read `tests/test_notifications.py` to understand the existing test patterns, then append a test that verifies the `request_corrections` event includes a token link when the request has a token. The key assertion is that `render_email` is called with `token_link` template (or that the rendered body contains the link URL).

Since the notification system is tightly coupled (calls `send_mail`), test at the `render_email` + `notify` level.

Append to `tests/test_notifications.py`:

```python
async def test_request_corrections_includes_token_link():
    """When request_corrections fires and request has a token, the email should include the token link."""
    from not_dot_net.backend.notifications import notify
    from not_dot_net.config import org_config

    org_cfg = await org_config.get()

    class FakeRequest:
        created_by = None
        target_email = "newcomer@test.com"
        token = "test-corrections-token"
        data = {}

    class FakeMailSettings:
        smtp_host = ""

    sent_subjects = []
    sent_bodies = []

    async def fake_send(to, subject, body, settings):
        sent_subjects.append(subject)
        sent_bodies.append(body)

    import not_dot_net.backend.notifications as notif_module
    original_send = None
    try:
        import not_dot_net.backend.mail as mail_mod
        original_send = mail_mod.send_mail
        mail_mod.send_mail = fake_send

        from not_dot_net.config import WorkflowConfig, WorkflowStepConfig, NotificationRuleConfig

        wf = WorkflowConfig(
            label="Onboarding",
            steps=[
                WorkflowStepConfig(key="newcomer_info", type="form", assignee="target_person", actions=["submit"]),
                WorkflowStepConfig(key="admin_validation", type="approval", actions=["approve", "request_corrections"], corrections_target="newcomer_info"),
            ],
            notifications=[
                NotificationRuleConfig(event="request_corrections", step="admin_validation", notify=["target_person"]),
            ],
        )

        recipients = await notify(
            request=FakeRequest(),
            event="request_corrections",
            step_key="admin_validation",
            workflow=wf,
            mail_settings=FakeMailSettings(),
            get_user_email=lambda uid: None,
            get_users_by_role=lambda r: [],
        )

        assert len(sent_bodies) == 1
        assert "test-corrections-token" in sent_bodies[0]
        assert recipients == ["newcomer@test.com"]
    finally:
        if original_send:
            mail_mod.send_mail = original_send
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_notifications.py::test_request_corrections_includes_token_link -v`
Expected: FAIL — the body won't contain the token because the current code uses the `request_corrections` template which has no link.

- [ ] **Step 3: Fix notify() to include token link for request_corrections**

In `not_dot_net/backend/notifications.py`, in the `notify()` function, change the template selection logic from:

```python
        # Determine template
        template_key = event
        kwargs = {}
        if event == "submit" and request.token:
            template_key = "token_link"
            kwargs["link"] = f"{base_url}/workflow/token/{request.token}"
```

to:

```python
        # Determine template
        template_key = event
        kwargs = {}
        if request.token and event in ("submit", "request_corrections"):
            template_key = "token_link" if event == "submit" else "corrections_with_link"
            kwargs["link"] = f"{base_url}/workflow/token/{request.token}"
```

And add a new template to the `TEMPLATES` dict:

```python
    "corrections_with_link": {
        "subject": "Corrections needed for your {workflow_label} submission",
        "body": "<p>The administration team has requested corrections on your "
                "<strong>{workflow_label}</strong> submission.</p>"
                '<p>Please visit the following link to update your information:</p>'
                '<p><a href="{link}">{link}</a></p>',
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_notifications.py::test_request_corrections_includes_token_link -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/notifications.py tests/test_notifications.py
git commit -m "fix: include token link in request_corrections notification email"
```

---

### Task 2: Add resend_notification service function

**Files:**
- Modify: `not_dot_net/backend/workflow_service.py`
- Create: `tests/test_resend_notification.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_resend_notification.py
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from not_dot_net.backend.db import User, get_async_session
from not_dot_net.backend.workflow_service import (
    create_request, submit_step, resend_notification, workflows_config, get_request_by_id,
)
from not_dot_net.backend.roles import RoleDefinition, roles_config


async def _create_user(email="staff@test.com", role="staff") -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(id=uuid.uuid4(), email=email, hashed_password="x", role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _setup_roles():
    cfg = await roles_config.get()
    cfg.roles["staff"] = RoleDefinition(label="Staff", permissions=["create_workflows"])
    cfg.roles["admin"] = RoleDefinition(
        label="Admin",
        permissions=["create_workflows", "approve_workflows", "access_personal_data", "manage_users"],
    )
    await roles_config.set(cfg)


async def test_resend_notification_regenerates_token():
    await _setup_roles()
    staff = await _create_user("staff@test.com", role="staff")

    req = await create_request(
        workflow_type="onboarding",
        created_by=staff.id,
        data={"contact_email": "newcomer@test.com", "status": "PhD", "employer": "CNRS"},
        actor=staff,
    )
    req = await submit_step(
        request_id=req.id, actor_id=staff.id, action="submit",
        data={"contact_email": "newcomer@test.com", "status": "PhD", "employer": "CNRS"},
        actor_user=staff,
    )
    old_token = req.token
    assert old_token is not None

    admin = await _create_user("admin@test.com", role="admin")
    updated = await resend_notification(req.id, actor_user=admin)

    assert updated.token is not None
    assert updated.token != old_token
    assert updated.token_expires_at > datetime.now(timezone.utc)


async def test_resend_notification_requires_permission():
    await _setup_roles()
    staff = await _create_user("staff2@test.com", role="staff")

    req = await create_request(
        workflow_type="onboarding",
        created_by=staff.id,
        data={"contact_email": "newcomer2@test.com", "status": "PhD", "employer": "CNRS"},
        actor=staff,
    )
    req = await submit_step(
        request_id=req.id, actor_id=staff.id, action="submit",
        data={"contact_email": "newcomer2@test.com", "status": "PhD", "employer": "CNRS"},
        actor_user=staff,
    )

    other = await _create_user("nobody@test.com", role="staff")
    with pytest.raises(PermissionError):
        await resend_notification(req.id, actor_user=other)


async def test_resend_only_for_target_person_steps():
    """Resend should fail if current step is not assigned to target_person."""
    await _setup_roles()
    staff = await _create_user("staff3@test.com", role="staff")

    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
        actor=staff,
    )
    req = await submit_step(
        request_id=req.id, actor_id=staff.id, action="submit",
        data={"target_name": "Alice", "target_email": "alice@test.com"},
        actor_user=staff,
    )
    # VPN access goes to approval step (assignee_role=director), not target_person
    admin = await _create_user("admin3@test.com", role="admin")
    with pytest.raises(ValueError, match="not assigned to target_person"):
        await resend_notification(req.id, actor_user=admin)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_resend_notification.py -v`
Expected: FAIL — `ImportError: cannot import name 'resend_notification'`

- [ ] **Step 3: Implement resend_notification**

Add to `not_dot_net/backend/workflow_service.py`:

```python
async def resend_notification(
    request_id: uuid.UUID,
    actor_user=None,
) -> WorkflowRequest:
    """Regenerate token and re-send notification for the current step.

    Only works when the current step is assigned to target_person.
    Caller must have permission to act on the request (checked via can_user_act).
    """
    async with session_scope() as session:
        req = await session.get(WorkflowRequest, request_id)
        if req is None:
            raise ValueError(f"Request {request_id} not found")
        if req.status != RequestStatus.IN_PROGRESS:
            raise ValueError("Only in-progress requests can be re-notified")

        wf = await _get_workflow_config(req.type)

        # Permission check
        if actor_user is None:
            raise PermissionError("No actor provided")
        from not_dot_net.backend.workflow_engine import can_user_act
        step_config = None
        for s in wf.steps:
            if s.key == req.current_step:
                step_config = s
                break

        # Only allow resend for target_person steps
        if step_config is None or step_config.assignee != "target_person":
            raise ValueError(f"Current step '{req.current_step}' is not assigned to target_person")

        # Caller must be able to act on some step of this workflow (i.e. have relevant permission)
        if not await has_permissions(actor_user, APPROVE_WORKFLOWS) and not await has_permissions(actor_user, "access_personal_data") and not await has_permissions(actor_user, "manage_users"):
            raise PermissionError("Insufficient permissions to resend notification")

        # Regenerate token
        req.token = str(uuid.uuid4())
        cfg = await workflows_config.get()
        req.token_expires_at = datetime.now(timezone.utc) + timedelta(days=cfg.token_expiry_days)

        # Reset verification code state so newcomer can re-verify
        req.verification_code_hash = None
        req.code_expires_at = None
        req.code_attempts = 0

        await session.commit()
        await session.refresh(req)

        # Fire notification
        try:
            await _fire_notifications(req, "submit", req.current_step, wf)
        except Exception:
            logger.exception("Failed to send notification for resend on request %s", request_id)

        # Audit
        from not_dot_net.backend.audit import log_audit
        await log_audit(
            "workflow", "resend_notification",
            actor_id=actor_user.id, actor_email=actor_user.email,
            target_type="request", target_id=req.id,
            detail=f"step={req.current_step}",
        )

        return req
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_resend_notification.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/workflow_service.py tests/test_resend_notification.py
git commit -m "feat: add resend_notification service for target_person steps"
```

---

### Task 3: i18n keys for resend button

**Files:**
- Modify: `not_dot_net/frontend/i18n.py`

- [ ] **Step 1: Add i18n keys**

In the EN `"Workflow"` section of `i18n.py`, add:

```python
        "resend_notification": "Resend Notification",
        "notification_resent": "Notification resent with new link",
        "resend_confirm": "Resend the token link to {email}?",
```

In the FR `"Workflow"` section, add:

```python
        "resend_notification": "Renvoyer la notification",
        "notification_resent": "Notification renvoyée avec un nouveau lien",
        "resend_confirm": "Renvoyer le lien au jeton à {email} ?",
```

- [ ] **Step 2: Run i18n tests**

Run: `uv run pytest tests/test_i18n.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/i18n.py
git commit -m "feat: add i18n keys for resend notification button (EN + FR)"
```

---

### Task 4: Add "Resend Notification" button to workflow detail

**Files:**
- Modify: `not_dot_net/frontend/workflow_detail.py`

- [ ] **Step 1: Add resend button to the action panel**

In `not_dot_net/frontend/workflow_detail.py`, modify the `_render_action_panel` function. After the approval section (after the `render_approval(...)` call at line 256), add a resend button. The button should appear when:
- The request is in progress
- The current step is assigned to `target_person`
- The user has relevant permissions (the service function checks this)

Find the end of the `if step_config.type == "approval":` block (after `render_approval(...)` at line 256). Add after it, but still inside `_render_action_panel`, before the `elif step_config.type == "form":` block:

Actually, the resend button should appear outside the approval/form conditional — it's an admin action independent of step type. Add it at the end of `_render_action_panel`, after both the approval and form blocks:

```python
        # Resend notification button — shown when current step is for target_person
        if step_config.assignee == "target_person" and req.target_email:
            ui.separator().classes("my-2")
            with ui.row().classes("items-center gap-2"):
                async def handle_resend():
                    from not_dot_net.backend.workflow_service import resend_notification
                    try:
                        await resend_notification(req.id, actor_user=user)
                    except Exception as e:
                        ui.notify(str(e), color="negative")
                        return
                    ui.notify(t("notification_resent"), color="positive")
                    ui.navigate.to(f"/workflow/request/{request_id_str}")

                ui.button(
                    t("resend_notification"), icon="send",
                    on_click=handle_resend,
                ).props("flat color=primary size=sm")
                ui.label(f"→ {req.target_email}").classes("text-xs text-grey")
```

But wait — the resend button should also be visible to admins who can't currently "act" on the step (since the current step is for target_person, not for them). The current code only renders the action panel if `can_act` is True. We need to show the resend button even when `can_act` is False, as long as the user has admin permissions.

So modify the detail_page function in `setup()`. After the existing action panel block (lines 95-103), add a separate check:

```python
            # Resend notification button for admin — even if they can't act on the step
            if (
                step_config
                and req.status == "in_progress"
                and step_config.assignee == "target_person"
                and req.target_email
            ):
                from not_dot_net.backend.permissions import has_permissions as _has_perms
                can_resend = await _has_perms(user, "approve_workflows") or await _has_perms(user, "access_personal_data") or await _has_perms(user, "manage_users")
                if can_resend:
                    with ui.card().classes("w-full q-pa-md mt-2").style(
                        "background: #fff8e1; border: 1px solid #ffe082;"
                    ):
                        with ui.row().classes("items-center gap-2"):
                            async def handle_resend():
                                from not_dot_net.backend.workflow_service import resend_notification
                                try:
                                    await resend_notification(req.id, actor_user=user)
                                except Exception as e:
                                    ui.notify(str(e), color="negative")
                                    return
                                ui.notify(t("notification_resent"), color="positive")
                                ui.navigate.to(f"/workflow/request/{request_id_str}")

                            ui.button(
                                t("resend_notification"), icon="send",
                                on_click=handle_resend,
                            ).props("flat color=primary size=sm")
                            ui.label(f"→ {req.target_email}").classes("text-xs text-grey")
```

This block goes in the `detail_page` function, after the existing action panel `if` block (after line 103), and still inside the `with ui.column()` context.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add not_dot_net/frontend/workflow_detail.py
git commit -m "feat: add resend notification button on workflow detail page"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS

- [ ] **Step 2: Manual verification**

Start dev server: `uv run python -m not_dot_net.cli serve --host localhost --port 8000`

Test the flow:
1. Create an onboarding request (initiation step with email, status, employer)
2. Submit it — newcomer gets a token link email
3. Use the token link to fill newcomer info and submit
4. As admin on `admin_validation` step, click "Request Corrections"
5. Verify: newcomer receives an email with a **new** token link (not "visit the link you received previously")
6. Verify: the new token link works
7. On the request detail page, verify the "Resend Notification" button appears
8. Click it — verify newcomer gets another email with yet another fresh link
