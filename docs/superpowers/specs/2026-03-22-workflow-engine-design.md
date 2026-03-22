# Workflow Engine, Roles, Notifications & Dashboard

## Goal

Replace the hardcoded onboarding form with a generic, YAML-driven workflow engine that supports multi-step processes (forms, approvals), role-based access, email notifications, and a user dashboard. First two workflow types: onboarding and VPN access requests.

## Context

The app currently has a single `OnboardingRequest` model with a dedicated UI tab. Users are either regular or superuser. There is no mail system and no dashboard. This design generalizes the request/approval pattern so new workflow types can be added via config without code changes.

---

## 1. User Roles

### Role Enum

Added to the `User` model as a `role` column:

| Role | Permissions |
|------|-------------|
| `member` | View directory, see own dashboard, complete steps assigned to them |
| `staff` | Create workflow requests, edit own profile. Inherits member. |
| `director` | Approve/reject requests assigned to director role. Inherits staff. |
| `admin` | Full system access. Inherits all. |

Roles are exclusive (one per user) and ordered. A permission check is `has_role(user, minimum_role)` — a director passes a staff check.

The existing `is_superuser` field (FastAPI-Users) is kept in sync: set to `True` when role is `admin`, `False` otherwise. This preserves compatibility with FastAPI-Users internals.

### Migration

- Existing users default to `member`.
- The seeded admin user gets `admin`.
- Fake dev users get varied roles for testing.

### New Files

- `backend/roles.py` — `Role` enum, `has_role(user, minimum_role) -> bool`.

### Modified Files

- `backend/db.py` — add `role` column to User.
- `backend/schemas.py` — add `role` to `UserRead`, `UserUpdate`.
- `backend/users.py` — set role on admin seed, sync `is_superuser`.

---

## 2. Workflow Data Model

### Tables

**`workflow_request`** — one row per workflow instance:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID, PK | |
| `type` | String | Workflow type key (e.g. `onboarding`, `vpn_access`) |
| `current_step` | String | Key of the active step |
| `status` | String | `in_progress`, `completed`, `rejected`, `cancelled` |
| `data` | JSON | Accumulated form data from all steps |
| `created_by` | FK → User, nullable | The requester |
| `target_email` | String, nullable | For workflows about a person who may not have an account |
| `token` | String, nullable | Secure token for external access to current step |
| `token_expires_at` | Timestamp, nullable | Token expiry (default: 30 days from generation) |
| `created_at` | Timestamp | |
| `updated_at` | Timestamp | |

**`workflow_event`** — audit log of every state change:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID, PK | |
| `request_id` | FK → workflow_request | |
| `step_key` | String | Which step this event is about |
| `action` | String | `submit`, `approve`, `reject`, `save_draft` |
| `actor_id` | FK → User, nullable | Null for token-based actors |
| `actor_token` | String, nullable | For external participants |
| `data_snapshot` | JSON, nullable | Form data at this point |
| `comment` | String, nullable | |
| `created_at` | Timestamp | |

**`workflow_file`** — uploaded documents:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID, PK | |
| `request_id` | FK → workflow_request | |
| `step_key` | String | |
| `field_name` | String | Which form field this file belongs to |
| `filename` | String | Original filename |
| `storage_path` | String | Path on disk |
| `uploaded_by` | FK → User, nullable | |
| `uploaded_at` | Timestamp | |

### Migration

The existing `onboarding_request` table is dropped. Since there is no production data yet, no data migration is needed — tables are recreated on startup.

### New Files

- `backend/workflow_models.py` — `WorkflowRequest`, `WorkflowEvent`, `WorkflowFile` SQLAlchemy models.

### Removed Files

- `backend/onboarding.py` — replaced by `workflow_models.py`.
- `backend/onboarding_router.py` — replaced by `workflow_service.py`.

---

## 3. Workflow Definitions (YAML Config)

Workflows are defined in the app's config YAML. The engine reads the config at runtime — no code changes needed to add a new workflow type.

### Config Structure

Each workflow definition has a `start_role` field that controls who can create new instances of that workflow type. Only users with that role (or higher) see it in the New Request page.

Each workflow can declare a `target_email_field` — the name of a form field in the first step whose value is copied to `workflow_request.target_email` on creation. This is how `assignee: target_person` gets resolved in later steps.

```yaml
workflows:
  vpn_access:
    label: VPN Access Request
    start_role: staff
    target_email_field: target_email
    steps:
      - key: request
        type: form
        assignee_role: staff
        fields:
          - {name: target_name, type: text, required: true, label: Person Name}
          - {name: target_email, type: email, required: true, label: Person Email}
          - {name: justification, type: textarea, required: false, label: Justification}
        actions: [submit]
      - key: approval
        type: approval
        assignee_role: director
        actions: [approve, reject]
    notifications:
      - event: submit
        step: request
        notify: [director]
      - event: approve  # no step field = matches this event on any step
        notify: [requester, target_person]
      - event: reject
        notify: [requester]

  onboarding:
    label: Onboarding
    start_role: staff
    target_email_field: person_email
    steps:
      - key: request
        type: form
        assignee_role: staff
        fields:
          - {name: person_name, type: text, required: true}
          - {name: person_email, type: email, required: true}
          - {name: role_status, type: select, options_key: roles, required: true}
          - {name: team, type: select, options_key: teams, required: true}
          - {name: start_date, type: date, required: true}
          - {name: note, type: textarea, required: false}
        actions: [submit]
      - key: newcomer_info
        type: form
        assignee: target_person
        partial_save: true
        fields:
          - {name: id_document, type: file, required: true, label: ID Copy}
          - {name: rib, type: file, required: true, label: Bank Details (RIB)}
          - {name: photo, type: file, required: false, label: Badge Photo}
          - {name: phone, type: text, required: true}
          - {name: emergency_contact, type: text, required: true}
        actions: [submit]
      - key: admin_validation
        type: approval
        assignee_role: admin
        actions: [approve, reject]
    notifications:
      - event: submit
        step: request
        notify: [target_person]
      - event: submit
        step: newcomer_info
        notify: [admin]
      - event: approve
        notify: [requester, target_person]
      - event: reject
        notify: [requester]
```

### Step Types

| Type | Behavior |
|------|----------|
| `form` | Renders fields from config, collects data. `partial_save: true` enables save-and-resume. |
| `approval` | Shows accumulated data as read-only with approve/reject buttons + optional comment. |

### Assignee Resolution

| Config | Resolution |
|--------|-----------|
| `assignee_role: director` | Any active user with that role (or higher) |
| `assignee: target_person` | Resolved via `target_email` on the workflow request |
| `assignee: requester` | The user who created the request |
| `assignee: step:<key>:actor` | Whoever completed a specific earlier step |

### Field Types

`text`, `email`, `textarea`, `date`, `select` (with `options_key` referencing a named list in the app settings — e.g. `teams` resolves to `Settings.teams`, `roles` resolves to the `Role` enum values), `file`.

### Modified Files

- `config.py` — add `workflows` dict and `mail` settings to `Settings`. Workflow definitions are loaded from the YAML config file and validated with Pydantic models.

---

## 4. Workflow Step Machine

The core logic that drives step transitions. Pure functions — no UI, no DB side effects.

### Responsibilities

Given a workflow request + workflow config, the engine determines:
- What is the current step?
- Who can act on it?
- What actions are available?
- Given an action, what is the next step (or terminal state)?

### Transition Rules

| Action | Effect |
|--------|--------|
| `submit` on a form step | Advance to next step in the list |
| `approve` on an approval step | Advance to next step, or `completed` if last step |
| `reject` on any step | Workflow status → `rejected` (terminal) |
| `save_draft` on a form step with `partial_save: true` | Stay on same step, update data |

### On Each Transition

1. Validate the action is allowed (correct actor, correct step).
2. Create a `workflow_event` record.
3. Merge form data into `workflow_request.data`.
4. Update `current_step` (or `status` if terminal).
5. Fire notifications for the event.
6. If next step has `assignee: target_person` and target has no account → generate token and send link.

### Completion Check (Form Steps)

For steps with `partial_save: true`, `submit` is only available when all required fields are filled and all required file uploads are present. The engine provides `get_completion_status(request, step_config) -> dict[str, bool]` returning done/missing per field.

### New Files

- `backend/workflow_engine.py` — pure functions: `get_available_actions()`, `validate_transition()`, `compute_next_step()`, `get_completion_status()`.
- `backend/workflow_service.py` — DB operations that call the engine then persist: `create_request()`, `submit_step()`, `save_draft()`, `list_requests()`, `list_actionable()`.

---

## 5. Token-Based External Access

For steps assigned to `target_person` who may not have an account.

### Flow

1. Workflow advances to a step with `assignee: target_person`.
2. Engine generates a UUID token, stores it on the workflow request.
3. Notification system emails a link: `/workflow/token/<token>`.
4. Recipient opens the link — sees only their step's form, no login required.
5. Form saves data with `actor_token` (not `actor_id`) in the event log.
6. Token is valid until the step is submitted. Reusable for partial saves.
7. Tokens expire after a configurable duration (default: 30 days).

### Security

- Tokens are long random UUIDs — not guessable.
- Token grants access to one specific step of one specific request.
- Uploaded files are stored under a path namespaced by request ID.
- No account creation until the workflow completes.

### New Files

- `frontend/workflow_token.py` — standalone NiceGUI page at `/workflow/token/<token>`.

### Token Storage

The `token` and `token_expires_at` columns on `workflow_request` (see Section 2) are set when a token-assigned step becomes active. Nulled out when the step is submitted. Regenerated if the step is revisited.

---

## 6. Notification / Mail System

### Mail Service

Async function `send_mail(to, subject, body_html)` backed by `aiosmtplib`.

### Config

```yaml
mail:
  smtp_host: smtp.polytechnique.fr
  smtp_port: 587
  smtp_tls: true
  smtp_user: ""
  smtp_password: ""
  from_address: noreply@lpp.polytechnique.fr
  dev_mode: false
  dev_catch_all: ""
```

- `dev_mode: true` → emails logged to console, not sent.
- `dev_catch_all` set → all mails redirected to that address.

### Notification Engine

On each workflow event:

1. Workflow engine calls `notify(request, event, step_key)`.
2. Look up matching notification rules from the workflow YAML config.
3. Resolve targets:
   - `requester` → `request.created_by.email`
   - `target_person` → `request.target_email`
   - Role name (e.g. `director`) → query all active users with that role
4. Render email from template.
5. Send via mail service.

### Email Templates

Predefined templates as Python strings in the notifications module:

| Template | Subject |
|----------|---------|
| `request_created` | A new {workflow_label} request needs your attention |
| `request_approved` | Your {workflow_label} request has been approved |
| `request_rejected` | Your {workflow_label} request was rejected |
| `step_assigned` | Action required: {step_label} for {workflow_label} |
| `token_link` | Please complete your information: {link} |

### New Files

- `backend/mail.py` — `send_mail()` with SMTP/dev mode.
- `backend/notifications.py` — notification engine + templates.

---

## 7. Dashboard & UI

### Tab Structure

Header tabs change from `People | Onboarding` to `People | Dashboard | New Request`.

The Onboarding tab is removed — onboarding is now a workflow type accessible via New Request.

### Dashboard Tab

Two sections:

**My Requests** — workflows I created, sorted by most recent. Each card shows: workflow type label, target person, current step label, status badge. Click to expand: full event history + current step details.

**Awaiting My Action** — steps assigned to me by role or as contextual participant. Each card shows: workflow type, requester, step label, since when. Click opens the step form or approval view inline.

### New Request Page

Lists available workflow types the user can start, filtered by role (e.g. only `staff+` see VPN access). Clicking a type opens the first step's form.

### Token Page

Standalone page at `/workflow/token/<token>`. No header, no tabs. Clean form for the assigned step with progress indicator for partial-save steps.

### Visibility Rules

| Role | Dashboard: My Requests | Dashboard: Awaiting Action | New Request |
|------|----------------------|---------------------------|-------------|
| `member` | Own requests | Steps assigned to them | No |
| `staff` | Own requests | Steps assigned to them | Yes |
| `director` | Own requests | Approval queue + own steps | Yes |
| `admin` | All requests | All pending steps | Yes |

### New Files

- `frontend/dashboard.py` — Dashboard tab.
- `frontend/new_request.py` — workflow type picker + first step form.
- `frontend/workflow_step.py` — renders a step (form or approval), reused by dashboard and token page.
- `frontend/workflow_token.py` — standalone token page.

### Modified Files

- `frontend/shell.py` — replace Onboarding tab, add Dashboard + New Request, show tabs based on role.
- `frontend/i18n.py` — add translation keys for workflow UI.

### Removed Files

- `frontend/onboarding.py` — replaced by new_request + workflow_step.

---

## 8. File Structure Summary

### New Files

| File | Purpose |
|------|---------|
| `backend/roles.py` | Role enum, `has_role()` |
| `backend/workflow_models.py` | WorkflowRequest, WorkflowEvent, WorkflowFile models |
| `backend/workflow_engine.py` | Pure step machine logic |
| `backend/workflow_service.py` | DB operations for workflows |
| `backend/mail.py` | Async mail sending |
| `backend/notifications.py` | Event-driven notification engine + templates |
| `frontend/dashboard.py` | Dashboard tab |
| `frontend/new_request.py` | Workflow type picker + first step form |
| `frontend/workflow_step.py` | Step renderer (form/approval) |
| `frontend/workflow_token.py` | Standalone token page |

### Modified Files

| File | Changes |
|------|---------|
| `backend/db.py` | Add `role` to User, import new models |
| `backend/schemas.py` | Add `role` to UserRead/UserUpdate |
| `backend/users.py` | Role on seed users, sync `is_superuser` |
| `config.py` | Add `mail` settings, `workflows` config with Pydantic validation |
| `frontend/shell.py` | New tab structure, role-based visibility |
| `frontend/i18n.py` | Workflow translation keys |

### Removed Files

| File | Reason |
|------|--------|
| `backend/onboarding.py` | Replaced by workflow_models |
| `backend/onboarding_router.py` | Replaced by workflow_service |
| `frontend/onboarding.py` | Replaced by new_request + workflow_step |
