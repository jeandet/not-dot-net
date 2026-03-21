# UI Redesign — Design Spec

## Overview

Redesign the not-dot-net intranet UI from placeholder tabs to a functional people directory with onboarding initiation. Built entirely with NiceGUI components + Tailwind CSS. No custom JS or CSS files.

## Pages

### 1. App Shell (all authenticated pages)

Top nav bar using `ui.header` + `ui.tabs`:

```
┌─────────────────────────────────────────────────┐
│  LPP Intranet    [People] [Onboarding]    👤 ▼  │
├─────────────────────────────────────────────────┤
│              Page content here                  │
└─────────────────────────────────────────────────┘
```

- App name on the left, tabs in the center, user dropdown on the right
- User dropdown: "My Profile" (scrolls to / expands own card), "Logout"
- Tabs are role-aware: "Onboarding" visible to all logged-in users
- No footer, no drawer
- People tab is the default / home page at route `/`

### 2. People Directory (home page, `/`)

**Search bar**: Single input at the top, filters cards client-side by name, team, office, email. Lab is <500 people so no pagination needed.

**Card grid**: Responsive grid layout (3-4 cols desktop, 2 tablet, 1 mobile). Each card shows:
- Avatar placeholder (or photo later)
- Full name
- Team/department
- Office number

**Expandable cards**: Clicking a card expands it in place to show full details:
- Phone, email, status (permanent, PhD, intern, visitor...), role/title
- Only one card expanded at a time (clicking another collapses the current one)
- Close button or click again to collapse

**Self-edit**: When viewing your own expanded card, an "Edit" button appears. Switches card to edit mode inline:
- Editable fields (v1): phone, office number
- Read-only fields: name, email, team
- Save / Cancel buttons
- On save: API call, collapse card, toast notification

**Superuser edit**: Users with `is_superuser=True` see "Edit" on every card and can edit all fields (including name, email, team). They also see a "Delete" button (with confirmation dialog).

### 3. Onboarding (`/` — Onboarding tab)

A form to initiate bringing a new person into the lab. This is the first step of a future multi-step workflow.

**Form fields**:
- New person's name (text input)
- New person's email (email input)
- Expected role/status (dropdown: researcher, PhD student, intern, visitor)
- Team/department (dropdown)
- Expected start date (date picker)
- Optional note/comment (textarea)

**On submit**: Record saved to DB with status "pending". Toast confirmation. No email/link/workflow yet — future work.

**Request list**: Below the form, a list of existing onboarding requests. Regular users see their own requests only. Superusers see all.

**Access**: Any logged-in user can create a request.

### 4. Login Page (`/login`)

Standalone page, no nav bar. Centered card:
- "LPP Intranet" title above the card
- Email + password inputs
- Login button
- No registration link (users come from AD or are created by superusers)
- Error feedback via toast notifications

No changes to auth logic — visual refresh only.

## Data Model Changes

**Person directory**: The current `User` model (from FastAPI-Users) stores auth info. Directory profiles need additional fields. Two options:
- Extend the User model with profile columns (phone, office, team, title, status)
- Separate `Profile` model linked to User

Extending User is simpler and sufficient for v1 since every directory entry is a user.

**New fields on User model**:
- `phone: Optional[str]`
- `office: Optional[str]`
- `team: Optional[str]`
- `title: Optional[str]`
- `status: Optional[str]` (permanent, PhD, intern, visitor)
- `full_name: Optional[str]`

**Onboarding request model** (new table):
- `id: UUID`
- `created_by: UUID` (FK to User)
- `person_name: str`
- `person_email: str`
- `role_status: str`
- `team: str`
- `start_date: date`
- `note: Optional[str]`
- `status: str` (pending, for now — future: invited, completed, etc.)
- `created_at: datetime`

## API Endpoints

**Directory**:
- `GET /api/people` — list all users with profile info (authenticated)
- `PATCH /api/people/{id}` — update profile fields (self: limited fields, superuser: all fields)
- `DELETE /api/people/{id}` — superuser only

**Onboarding**:
- `POST /api/onboarding` — create request (any authenticated user)
- `GET /api/onboarding` — list requests (own for regular users, all for superusers)

## Technical Approach

- All UI built with NiceGUI components (`ui.card`, `ui.input`, `ui.grid`, `ui.tabs`, `ui.expansion`, etc.) and Tailwind classes
- Client-side search filtering using NiceGUI's binding/reactivity
- Existing auth system unchanged — `current_active_user` dependency used for all protected pages
- `is_superuser` flag used for permission checks (no new role system)
- SQLAlchemy async with existing engine/session setup

## Out of Scope (future work)

- AD sync (periodic import from Active Directory)
- Full onboarding workflow (email, secure link, document upload)
- Photo upload
- Role-based access beyond superuser
- Team/department management UI
- News/announcements section
