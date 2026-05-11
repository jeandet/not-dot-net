# Workflow Notifications Implementation Plan (Part 2: Mail + Notifications)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement async mail sending and event-driven notifications that fire on workflow transitions, resolving recipients from config rules and delivering via SMTP or dev-mode logging.

**Architecture:** `mail.py` is a thin async wrapper around `aiosmtplib` with dev-mode logging. `notifications.py` matches workflow events against config rules, resolves recipients, renders templates, and calls the mail service. The service layer (`workflow_service.py`) calls `notify()` after each transition.

**Tech Stack:** aiosmtplib for SMTP, pytest with monkeypatch for testing (no real SMTP).

**Spec:** `docs/superpowers/specs/2026-03-22-workflow-engine-design.md` — Section 6

**Spec deviations (intentional):**
- Template keys use action names (`submit`, `approve`, `reject`) instead of spec names (`request_created`, etc.) — this removes the need for a mapping layer since actions map 1:1 to templates.
- `token_link` subject uses `{workflow_label}` instead of `{link}` — a URL in the subject line is ugly.

---

### Task 1: Add aiosmtplib Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add aiosmtplib to dependencies**

Add `"aiosmtplib"` to the `dependencies` list in `pyproject.toml`.

- [ ] **Step 2: Install**

Run: `uv pip install -e .`

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "import aiosmtplib; print('ok')"`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add aiosmtplib dependency for mail sending"
```

---

### Task 2: Mail Service

**Files:**
- Create: `not_dot_net/backend/mail.py`
- Create: `tests/test_mail.py`

- [ ] **Step 1: Write failing tests for mail service**

```python
# tests/test_mail.py
import pytest
from unittest.mock import AsyncMock, patch
from not_dot_net.backend.mail import send_mail
from not_dot_net.config import MailSettings


async def test_dev_mode_logs_to_console(capsys):
    settings = MailSettings(dev_mode=True)
    await send_mail(
        to="user@example.com",
        subject="Test Subject",
        body_html="<p>Hello</p>",
        mail_settings=settings,
    )
    captured = capsys.readouterr()
    assert "user@example.com" in captured.out
    assert "Test Subject" in captured.out


async def test_dev_catch_all_redirects(capsys):
    settings = MailSettings(dev_mode=True, dev_catch_all="catch@example.com")
    await send_mail(
        to="real@example.com",
        subject="Test",
        body_html="<p>Hi</p>",
        mail_settings=settings,
    )
    captured = capsys.readouterr()
    assert "catch@example.com" in captured.out
    assert "real@example.com" in captured.out  # original still mentioned


async def test_production_mode_calls_aiosmtplib():
    settings = MailSettings(
        dev_mode=False,
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_tls=True,
        from_address="noreply@test.com",
    )
    with patch("not_dot_net.backend.mail.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await send_mail(
            to="user@example.com",
            subject="Prod Test",
            body_html="<p>Content</p>",
            mail_settings=settings,
        )
        mock_smtp.send.assert_called_once()
        msg = mock_smtp.send.call_args[0][0]
        assert msg["To"] == "user@example.com"
        assert msg["Subject"] == "Prod Test"
        assert msg["From"] == "noreply@test.com"


async def test_production_with_catch_all_redirects():
    settings = MailSettings(
        dev_mode=False,
        smtp_host="smtp.test.com",
        dev_catch_all="catch@example.com",
        from_address="noreply@test.com",
    )
    with patch("not_dot_net.backend.mail.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await send_mail(
            to="real@example.com",
            subject="Test",
            body_html="<p>Hi</p>",
            mail_settings=settings,
        )
        msg = mock_smtp.send.call_args[0][0]
        assert msg["To"] == "catch@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mail.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement mail.py**

```python
# not_dot_net/backend/mail.py
"""Async mail sending with dev-mode logging."""

from email.message import EmailMessage

import aiosmtplib

from not_dot_net.config import MailSettings


async def send_mail(
    to: str,
    subject: str,
    body_html: str,
    mail_settings: MailSettings,
) -> None:
    effective_to = to
    if mail_settings.dev_catch_all:
        effective_to = mail_settings.dev_catch_all

    if mail_settings.dev_mode:
        print(f"[MAIL dev] To: {effective_to} (original: {to})")
        print(f"[MAIL dev] Subject: {subject}")
        print(f"[MAIL dev] Body: {body_html[:200]}")
        return

    msg = EmailMessage()
    msg["From"] = mail_settings.from_address
    msg["To"] = effective_to
    msg["Subject"] = subject
    msg.set_content(body_html, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=mail_settings.smtp_host,
        port=mail_settings.smtp_port,
        start_tls=mail_settings.smtp_tls,
        username=mail_settings.smtp_user or None,
        password=mail_settings.smtp_password or None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mail.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/mail.py tests/test_mail.py
git commit -m "feat: add async mail service with dev-mode logging"
```

---

### Task 3: Notification Engine

**Files:**
- Create: `not_dot_net/backend/notifications.py`
- Create: `tests/test_notifications.py`

- [ ] **Step 1: Write failing tests for notification engine**

```python
# tests/test_notifications.py
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from not_dot_net.backend.notifications import notify, resolve_recipients, render_email
from not_dot_net.config import (
    WorkflowConfig,
    WorkflowStepConfig,
    NotificationRuleConfig,
    FieldConfig,
    MailSettings,
)
from not_dot_net.backend.roles import Role


# --- Fixtures ---

VPN_WORKFLOW = WorkflowConfig(
    label="VPN Access Request",
    start_role="staff",
    target_email_field="target_email",
    steps=[
        WorkflowStepConfig(key="request", type="form", assignee_role="staff", actions=["submit"]),
        WorkflowStepConfig(key="approval", type="approval", assignee_role="director", actions=["approve", "reject"]),
    ],
    notifications=[
        NotificationRuleConfig(event="submit", step="request", notify=["director"]),
        NotificationRuleConfig(event="approve", notify=["requester", "target_person"]),
        NotificationRuleConfig(event="reject", notify=["requester"]),
    ],
)


class FakeRequest:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid.uuid4())
        self.type = kwargs.get("type", "vpn_access")
        self.current_step = kwargs.get("current_step", "request")
        self.status = kwargs.get("status", "in_progress")
        self.data = kwargs.get("data", {})
        self.created_by = kwargs.get("created_by", uuid.uuid4())
        self.target_email = kwargs.get("target_email", "target@test.com")
        self.token = kwargs.get("token", None)


class FakeUser:
    def __init__(self, email, role=Role.DIRECTOR, id=None):
        self.email = email
        self.role = role
        self.id = id or uuid.uuid4()
        self.is_active = True


# --- Tests: rule matching ---

def test_matching_rules_by_event_and_step():
    from not_dot_net.backend.notifications import _matching_rules
    rules = _matching_rules(VPN_WORKFLOW, "submit", "request")
    assert len(rules) == 1
    assert "director" in rules[0].notify


def test_matching_rules_event_only():
    from not_dot_net.backend.notifications import _matching_rules
    rules = _matching_rules(VPN_WORKFLOW, "approve", "approval")
    assert len(rules) == 1
    assert "requester" in rules[0].notify


def test_matching_rules_no_match():
    from not_dot_net.backend.notifications import _matching_rules
    rules = _matching_rules(VPN_WORKFLOW, "save_draft", "request")
    assert len(rules) == 0


# --- Tests: recipient resolution ---

async def test_resolve_requester():
    requester_id = uuid.uuid4()
    req = FakeRequest(created_by=requester_id)

    async def mock_get_email(user_id):
        return "requester@test.com"

    emails = await resolve_recipients(
        ["requester"], req, get_user_email=mock_get_email, get_users_by_role=AsyncMock(return_value=[]),
    )
    assert "requester@test.com" in emails


async def test_resolve_target_person():
    req = FakeRequest(target_email="newcomer@test.com")

    emails = await resolve_recipients(
        ["target_person"], req, get_user_email=AsyncMock(), get_users_by_role=AsyncMock(return_value=[]),
    )
    assert "newcomer@test.com" in emails


async def test_resolve_role():
    req = FakeRequest()

    async def mock_get_by_role(role_str):
        return [FakeUser("dir1@test.com"), FakeUser("dir2@test.com")]

    emails = await resolve_recipients(
        ["director"], req, get_user_email=AsyncMock(), get_users_by_role=mock_get_by_role,
    )
    assert "dir1@test.com" in emails
    assert "dir2@test.com" in emails


# --- Tests: email rendering ---

def test_render_submit_email():
    subject, body = render_email("submit", "VPN Access Request", step_label="Request")
    assert "VPN Access Request" in subject
    assert "VPN Access Request" in body


def test_render_approve_email():
    subject, body = render_email("approve", "VPN Access Request")
    assert "approved" in subject.lower()


def test_render_reject_email():
    subject, body = render_email("reject", "VPN Access Request")
    assert "rejected" in subject.lower()


def test_render_token_link_email():
    subject, body = render_email("token_link", "Onboarding", link="http://localhost/workflow/token/abc123")
    assert "http://localhost/workflow/token/abc123" in body


def test_render_unknown_event_raises():
    with pytest.raises(ValueError, match="No email template"):
        render_email("unknown_event", "Test Workflow")


# --- Tests: full notify pipeline ---

async def test_notify_sends_to_resolved_recipients():
    """Test the full notify() pipeline: rule matching -> resolution -> rendering -> sending."""
    req = FakeRequest(
        type="vpn_access",
        current_step="request",
        target_email="target@test.com",
        created_by=uuid.uuid4(),
    )

    sent_emails = []

    async def fake_send_mail(to, subject, body_html, mail_settings):
        sent_emails.append((to, subject))

    with patch("not_dot_net.backend.notifications.send_mail", side_effect=fake_send_mail):
        result = await notify(
            request=req,
            event="submit",
            step_key="request",
            workflow=VPN_WORKFLOW,
            mail_settings=MailSettings(dev_mode=True),
            get_user_email=AsyncMock(return_value="requester@test.com"),
            get_users_by_role=AsyncMock(return_value=[FakeUser("dir@test.com")]),
        )

    assert "dir@test.com" in result
    assert len(sent_emails) == 1
    assert "dir@test.com" == sent_emails[0][0]
    assert "VPN Access Request" in sent_emails[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement notifications.py**

```python
# not_dot_net/backend/notifications.py
"""Event-driven notification engine for workflow transitions."""

from not_dot_net.config import WorkflowConfig, NotificationRuleConfig


# --- Email Templates ---

TEMPLATES = {
    "submit": {
        "subject": "A new {workflow_label} request needs your attention",
        "body": "<p>A new <strong>{workflow_label}</strong> request has been submitted"
                " and requires your action.</p>",
    },
    "approve": {
        "subject": "Your {workflow_label} request has been approved",
        "body": "<p>Your <strong>{workflow_label}</strong> request has been approved.</p>",
    },
    "reject": {
        "subject": "Your {workflow_label} request was rejected",
        "body": "<p>Your <strong>{workflow_label}</strong> request was rejected.</p>",
    },
    "step_assigned": {
        "subject": "Action required: {step_label} for {workflow_label}",
        "body": "<p>You have a pending action on <strong>{workflow_label}</strong>: "
                "{step_label}.</p>",
    },
    "token_link": {
        "subject": "Please complete your information for {workflow_label}",
        "body": "<p>Please complete your information by visiting the link below:</p>"
                '<p><a href="{link}">{link}</a></p>',
    },
}


def render_email(event: str, workflow_label: str, **kwargs) -> tuple[str, str]:
    """Render an email template. Returns (subject, body_html)."""
    template = TEMPLATES.get(event)
    if template is None:
        raise ValueError(f"No email template for event: {event}")
    subject = template["subject"].format(workflow_label=workflow_label, **kwargs)
    body = template["body"].format(workflow_label=workflow_label, **kwargs)
    return subject, body


def _matching_rules(
    workflow: WorkflowConfig, event: str, step_key: str
) -> list[NotificationRuleConfig]:
    """Find notification rules that match this event + step."""
    matched = []
    for rule in workflow.notifications:
        if rule.event != event:
            continue
        if rule.step is not None and rule.step != step_key:
            continue
        matched.append(rule)
    return matched


async def resolve_recipients(
    notify_targets: list[str],
    request,
    get_user_email,
    get_users_by_role,
) -> list[str]:
    """Resolve notification targets to email addresses.

    Args:
        notify_targets: list of "requester", "target_person", or role names
        request: the workflow request object
        get_user_email: async fn(user_id) -> email
        get_users_by_role: async fn(role_str) -> list[User]
    """
    emails = set()
    for target in notify_targets:
        if target == "requester" and request.created_by:
            email = await get_user_email(request.created_by)
            if email:
                emails.add(email)
        elif target == "target_person" and request.target_email:
            emails.add(request.target_email)
        else:
            users = await get_users_by_role(target)
            for user in users:
                emails.add(user.email)
    return list(emails)


async def notify(
    request,
    event: str,
    step_key: str,
    workflow: WorkflowConfig,
    mail_settings,
    get_user_email,
    get_users_by_role,
    base_url: str = "http://localhost:8088",
) -> list[str]:
    """Fire notifications for a workflow event. Returns list of emails sent to."""
    from not_dot_net.backend.mail import send_mail

    rules = _matching_rules(workflow, event, step_key)
    if not rules:
        return []

    all_sent = []
    for rule in rules:
        recipients = await resolve_recipients(
            rule.notify, request, get_user_email, get_users_by_role,
        )

        # Determine template
        template_key = event
        kwargs = {}
        if event == "submit" and request.token:
            template_key = "token_link"
            kwargs["link"] = f"{base_url}/workflow/token/{request.token}"

        subject, body = render_email(template_key, workflow.label, **kwargs)

        for email in recipients:
            await send_mail(email, subject, body, mail_settings)
            all_sent.append(email)

    return all_sent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/notifications.py tests/test_notifications.py
git commit -m "feat: add event-driven notification engine with email templates"
```

---

### Task 4: Wire Notifications into Workflow Service

**Files:**
- Modify: `not_dot_net/backend/workflow_service.py`
- Create: `tests/test_workflow_notifications_integration.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_workflow_notifications_integration.py
import pytest
import uuid
from unittest.mock import patch, AsyncMock
from not_dot_net.backend.workflow_service import create_request, submit_step
from not_dot_net.backend.roles import Role
from not_dot_net.backend.db import Base, User, get_async_session
from not_dot_net.config import init_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from contextlib import asynccontextmanager
import not_dot_net.backend.db as db_module
import not_dot_net.backend.workflow_models  # noqa: F401


@pytest.fixture(autouse=True)
async def setup_db():
    init_settings()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    old_engine, old_session = db_module._engine, db_module._async_session_maker
    db_module._engine = engine
    db_module._async_session_maker = session_maker
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    db_module._engine, db_module._async_session_maker = old_engine, old_session


async def _create_user(email="staff@test.com", role=Role.STAFF) -> User:
    get_session = asynccontextmanager(get_async_session)
    async with get_session() as session:
        user = User(id=uuid.uuid4(), email=email, hashed_password="x", role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_submit_step_fires_notifications():
    """After submitting the request step of vpn_access, directors should be notified."""
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)

    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )

    with patch("not_dot_net.backend.workflow_service.notify", new_callable=AsyncMock) as mock_notify:
        mock_notify.return_value = ["director@test.com"]
        await submit_step(req.id, staff.id, "submit", data={})
        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["event"] == "submit"


async def test_approve_fires_notifications():
    staff = await _create_user(email="staff@test.com", role=Role.STAFF)
    director = await _create_user(email="director@test.com", role=Role.DIRECTOR)

    req = await create_request(
        workflow_type="vpn_access",
        created_by=staff.id,
        data={"target_name": "Alice", "target_email": "alice@test.com"},
    )

    # Submit first step (mock notifications)
    with patch("not_dot_net.backend.workflow_service.notify", new_callable=AsyncMock) as mock_notify:
        mock_notify.return_value = []
        req = await submit_step(req.id, staff.id, "submit", data={})

    # Approve (check notifications fire)
    with patch("not_dot_net.backend.workflow_service.notify", new_callable=AsyncMock) as mock_notify:
        mock_notify.return_value = []
        await submit_step(req.id, director.id, "approve", data={})
        mock_notify.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workflow_notifications_integration.py -v`
Expected: FAIL (notify not imported in workflow_service)

- [ ] **Step 3: Add notify call to workflow_service.py**

In `submit_step()`, after the commit + refresh, add notification firing:

```python
# At the end of submit_step, after await session.refresh(req):

        # Fire notifications (after commit, outside the session)
        try:
            await _fire_notifications(req, action, event.step_key, wf)
        except Exception:
            pass  # notifications are best-effort, don't fail the step

        return req
```

Add the helper function to `workflow_service.py`:

```python
async def _fire_notifications(req, event: str, step_key: str, wf):
    """Fire notifications for a workflow event. Best-effort.

    Note: each lookup opens a fresh session (N+1). Acceptable at current scale.
    """
    from not_dot_net.backend.notifications import notify
    from not_dot_net.backend.db import get_async_session, User
    from not_dot_net.backend.roles import Role as RoleEnum

    settings = get_settings()

    async def get_user_email(user_id):
        get_session = asynccontextmanager(get_async_session)
        async with get_session() as session:
            user = await session.get(User, user_id)
            return user.email if user else None

    async def get_users_by_role(role_str):
        get_session = asynccontextmanager(get_async_session)
        async with get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(
                    User.role == RoleEnum(role_str),
                    User.is_active == True,
                )
            )
            return list(result.scalars().all())

    await notify(
        request=req,
        event=event,
        step_key=step_key,
        workflow=wf,
        mail_settings=settings.mail,
        get_user_email=get_user_email,
        get_users_by_role=get_users_by_role,
    )
```

**Important:** The `notify` import and call should be inside the `_fire_notifications` helper, NOT at module level, to keep the import lazy and allow easy mocking in tests.

- [ ] **Step 4: Run integration tests**

Run: `uv run pytest tests/test_workflow_notifications_integration.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add not_dot_net/backend/workflow_service.py tests/test_workflow_notifications_integration.py
git commit -m "feat: wire notification engine into workflow step transitions"
```

---

## What's Next

**Plan 3: Dashboard & UI** (`2026-03-22-workflow-ui.md`)
- `frontend/dashboard.py` — My Requests + Awaiting Action
- `frontend/new_request.py` — workflow type picker + first step form
- `frontend/workflow_step.py` — form/approval step renderer
- `frontend/workflow_token.py` — standalone token page
- `frontend/shell.py` — new tab structure with role-based visibility
- `frontend/i18n.py` — workflow translation keys
