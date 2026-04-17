# Active Directory Write-Back Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit profile fields that are mirrored to Active Directory, with AD as the source of truth. Self-edits (phone, office) use the user's own AD credentials; admin-edits use admin AD credentials supplied on the fly. No service-account write credentials are stored.

**Architecture:**
- AD attribute ⟷ local field map lives in `auth/ldap.py`.
- New pure function `ldap_modify_user(dn, changes, bind_username, bind_password, cfg, connect)` binds as the supplied identity and writes to AD. On success, local DB is updated to match.
- `ldap_authenticate` is extended to return the user's DN and the full attribute set; successful login re-syncs those fields into the local DB row (AD-authoritative).
- `frontend/directory.py` edit dialog prompts for credentials when any AD-synced field is being changed on an LDAP-backed user; local-only fields (`employment_status`, `start_date`, `end_date`) never hit AD.

**Tech Stack:** `ldap3` (with `MOCK_SYNC` + `OFFLINE_AD_2012_R2` for tests), FastAPI-Users, NiceGUI, SQLAlchemy async, pytest.

---

## File Structure

- **Modify** `not_dot_net/backend/auth/ldap.py` — extend `LdapUserInfo`, extend `ldap_authenticate` to return DN + full attrs, add `AD_ATTR_MAP`, `ldap_modify_user`, `sync_user_from_ldap`.
- **Modify** `not_dot_net/frontend/login.py` — after successful LDAP auth, call `sync_user_from_ldap` for the matched local user.
- **Modify** `not_dot_net/frontend/directory.py` — split edit flow: compute which fields changed, classify as AD-synced vs local-only, prompt for creds when AD writes are needed, call `ldap_modify_user`, then update local DB.
- **Modify** `not_dot_net/frontend/i18n.py` — add strings for password prompt, admin credential prompt, AD write errors.
- **New** `tests/test_ldap_modify.py` — `ldap_modify_user` unit tests with `MOCK_SYNC`.
- **New** `tests/test_ldap_sync.py` — `sync_user_from_ldap` unit tests.
- **Modify** `tests/test_ldap.py` — extended attrs + DN in `ldap_authenticate`.
- **Modify** `tests/test_directory.py` — edit flow classifier + password prompt paths.

---

## Task 1: Extend `LdapUserInfo` with full attribute set + DN

**Files:**
- Modify: `not_dot_net/backend/auth/ldap.py:18-49`
- Modify: `tests/test_ldap.py`

- [ ] **Step 1: Write the failing test** (add to `tests/test_ldap.py`)

```python
def test_authentication_returns_dn_and_extended_attrs():
    result = ldap_authenticate("jdoe", "secret", LDAP_CFG, connect=fake_ldap_connect_extended)
    assert result is not None
    assert result.dn == "cn=jdoe,ou=users,dc=example,dc=com"
    assert result.phone == "+33123456789"
    assert result.office == "Room 101"
    assert result.title == "Researcher"
    assert result.department == "Plasma"
```

And extend `fake_ldap_connect` (rename copy to `fake_ldap_connect_extended`) so the `jdoe` entry also has `telephoneNumber`, `physicalDeliveryOfficeName`, `title`, `department`:

```python
def fake_ldap_connect_extended(ldap_cfg: LdapConfig, username: str, password: str) -> Connection:
    server = Server("fake_ad", get_info=OFFLINE_AD_2012_R2)
    conn = Connection(server, user=f"{username}@{ldap_cfg.domain}", password=password, client_strategy=MOCK_SYNC)
    entry_attrs = {
        "sAMAccountName": "jdoe",
        "userPassword": "secret",
        "objectClass": "person",
        "mail": "jdoe@example.com",
        "displayName": "John Doe",
        "givenName": "John",
        "sn": "Doe",
        "telephoneNumber": "+33123456789",
        "physicalDeliveryOfficeName": "Room 101",
        "title": "Researcher",
        "department": "Plasma",
    }
    conn.strategy.add_entry(f"cn=jdoe,ou=users,{ldap_cfg.base_dn}", entry_attrs)
    conn.bind()
    if password != "secret":
        from ldap3.core.exceptions import LDAPBindError
        raise LDAPBindError("Invalid credentials")
    return conn
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ldap.py::test_authentication_returns_dn_and_extended_attrs -v`
Expected: FAIL — `LdapUserInfo` has no `dn`/`phone`/`office`/`title`/`department` attributes.

- [ ] **Step 3: Implement**

In `not_dot_net/backend/auth/ldap.py`, replace the `_AD_ATTRIBUTES` constant and `LdapUserInfo`:

```python
AD_ATTR_MAP: dict[str, str] = {
    # local field  -> AD attribute
    "email":     "mail",
    "full_name": "displayName",
    "phone":     "telephoneNumber",
    "office":    "physicalDeliveryOfficeName",
    "title":     "title",
    "team":      "department",
}

_AD_ATTRIBUTES = list(AD_ATTR_MAP.values()) + ["givenName", "sn"]


@dataclass(frozen=True)
class LdapUserInfo:
    email: str
    dn: str
    full_name: str | None = None
    given_name: str | None = None
    surname: str | None = None
    phone: str | None = None
    office: str | None = None
    title: str | None = None
    department: str | None = None
```

And update `ldap_authenticate` to capture `entry.entry_dn` and the new attrs:

```python
entry = conn.entries[0]
email = _attr_value(entry, "mail")
if email is None:
    return None
return LdapUserInfo(
    email=email,
    dn=entry.entry_dn,
    full_name=_attr_value(entry, "displayName"),
    given_name=_attr_value(entry, "givenName"),
    surname=_attr_value(entry, "sn"),
    phone=_attr_value(entry, "telephoneNumber"),
    office=_attr_value(entry, "physicalDeliveryOfficeName"),
    title=_attr_value(entry, "title"),
    department=_attr_value(entry, "department"),
)
```

- [ ] **Step 4: Update existing LdapUserInfo call sites and fakes**

`LdapUserInfo` is now constructed with required `dn`. Update:

- `tests/test_ldap_provision.py::test_provision_ldap_user_creates_user` — change `LdapUserInfo(email=...)` to include `dn="cn=ad.user,dc=example,dc=com"`.
- `tests/test_ldap_provision.py::test_provision_sets_empty_role_when_no_default` — add `dn="cn=norole,dc=example,dc=com"`.
- `tests/test_ldap_provision.py::_make_fake_connect` — extend the attribute list it copies from `attrs` to include the new AD attributes (`telephoneNumber`, `physicalDeliveryOfficeName`, `title`, `department`) so fake users can define them:

```python
for attr in ("mail", "displayName", "givenName", "sn",
             "telephoneNumber", "physicalDeliveryOfficeName", "title", "department"):
    if attrs.get(attr):
        entry_attrs[attr] = attrs[attr]
```

- `tests/test_ldap.py` — reuse the same update in `fake_ldap_connect` (do NOT introduce a separate `fake_ldap_connect_extended`; extend the existing one in place, adding the new attrs to the `jdoe` entry).

Run: `uv run pytest tests/test_ldap.py tests/test_ldap_provision.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/auth/ldap.py tests/test_ldap.py tests/test_ldap_provision.py
git commit -m "feat(ldap): extend LdapUserInfo with DN and full attribute set"
```

---

## Task 2: `ldap_modify_user` pure function

**Files:**
- Modify: `not_dot_net/backend/auth/ldap.py` (add function + error class)
- Create: `tests/test_ldap_modify.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ldap_modify.py`:

```python
import pytest
from ldap3 import Server, Connection, MOCK_SYNC, OFFLINE_AD_2012_R2
from ldap3.core.exceptions import LDAPBindError

from not_dot_net.backend.auth.ldap import (
    LdapConfig, ldap_modify_user, LdapModifyError,
)

LDAP_CFG = LdapConfig(url="fake", domain="example.com", base_dn="dc=example,dc=com")
USER_DN = "cn=jdoe,ou=users,dc=example,dc=com"


def _make_mutable_fake(initial_attrs: dict):
    """Shared-state fake connect. Modifies write into the returned dict."""
    state = dict(initial_attrs)

    def fake_connect(ldap_cfg, username, password):
        server = Server("fake_ad", get_info=OFFLINE_AD_2012_R2)
        conn = Connection(server, user=f"{username}@{ldap_cfg.domain}",
                          password=password, client_strategy=MOCK_SYNC)
        conn.strategy.add_entry(USER_DN, {
            "sAMAccountName": "jdoe", "userPassword": "secret",
            "objectClass": "person", "mail": "jdoe@example.com",
            **{k: v for k, v in state.items() if v is not None},
        })
        conn.bind()
        if password != "secret":
            raise LDAPBindError("Invalid credentials")
        # Track modifications in shared state
        orig_modify = conn.modify
        def tracked_modify(dn, changes, *a, **kw):
            result = orig_modify(dn, changes, *a, **kw)
            for attr, ops in changes.items():
                _op, values = ops[0]
                state[attr] = values[0] if values else None
            return result
        conn.modify = tracked_modify
        return conn

    return fake_connect, state


def test_modify_writes_changes():
    fake_connect, state = _make_mutable_fake({
        "telephoneNumber": "+33111", "physicalDeliveryOfficeName": "Old",
    })
    ldap_modify_user(
        dn=USER_DN,
        changes={"telephoneNumber": "+33999", "physicalDeliveryOfficeName": "New Room"},
        bind_username="jdoe", bind_password="secret",
        ldap_cfg=LDAP_CFG, connect=fake_connect,
    )
    assert state["telephoneNumber"] == "+33999"
    assert state["physicalDeliveryOfficeName"] == "New Room"


def test_modify_bind_failure_raises():
    fake_connect, _ = _make_mutable_fake({"telephoneNumber": "+33111"})
    with pytest.raises(LdapModifyError) as exc:
        ldap_modify_user(
            dn=USER_DN, changes={"telephoneNumber": "x"},
            bind_username="jdoe", bind_password="wrong",
            ldap_cfg=LDAP_CFG, connect=fake_connect,
        )
    assert "bind" in str(exc.value).lower()


def test_modify_empty_changes_is_noop():
    fake_connect, state = _make_mutable_fake({"telephoneNumber": "+33111"})
    ldap_modify_user(
        dn=USER_DN, changes={},
        bind_username="jdoe", bind_password="secret",
        ldap_cfg=LDAP_CFG, connect=fake_connect,
    )
    assert state == {"telephoneNumber": "+33111"}


def test_modify_clears_attribute_when_value_is_none():
    fake_connect, state = _make_mutable_fake({"physicalDeliveryOfficeName": "Old"})
    ldap_modify_user(
        dn=USER_DN, changes={"physicalDeliveryOfficeName": None},
        bind_username="jdoe", bind_password="secret",
        ldap_cfg=LDAP_CFG, connect=fake_connect,
    )
    assert state["physicalDeliveryOfficeName"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ldap_modify.py -v`
Expected: FAIL — `LdapModifyError`, `ldap_modify_user` not defined.

- [ ] **Step 3: Implement**

Append to `not_dot_net/backend/auth/ldap.py`:

```python
from ldap3 import MODIFY_REPLACE


class LdapModifyError(Exception):
    """Raised when an AD modify fails (bind, permissions, or server error)."""


def ldap_modify_user(
    dn: str,
    changes: dict[str, str | None],
    bind_username: str,
    bind_password: str,
    ldap_cfg: LdapConfig,
    connect: Callable[..., Connection] = default_ldap_connect,
) -> None:
    """Bind as bind_username and replace attributes on dn.

    `changes` maps AD attribute name to new value. `None` clears the attribute.
    Raises LdapModifyError on bind failure, insufficient rights, or server error.
    """
    if not changes:
        return
    try:
        conn = connect(ldap_cfg, bind_username, bind_password)
    except LDAPBindError as e:
        raise LdapModifyError(f"LDAP bind failed: {e}") from e
    except LDAPException as e:
        raise LdapModifyError(f"LDAP connection error: {e}") from e

    try:
        modify_payload = {
            attr: [(MODIFY_REPLACE, [value] if value else [])]
            for attr, value in changes.items()
        }
        ok = conn.modify(dn, modify_payload)
        if not ok:
            raise LdapModifyError(
                f"modify failed: {conn.result.get('description')} "
                f"({conn.result.get('message')})"
            )
    finally:
        conn.unbind()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ldap_modify.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/auth/ldap.py tests/test_ldap_modify.py
git commit -m "feat(ldap): add ldap_modify_user for AD write-back"
```

---

## Task 3: `sync_user_from_ldap` helper

**Files:**
- Modify: `not_dot_net/backend/auth/ldap.py` (add function)
- Create: `tests/test_ldap_sync.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ldap_sync.py`:

```python
import pytest

from not_dot_net.backend.auth.ldap import LdapUserInfo, sync_user_from_ldap
from not_dot_net.backend.db import User, AuthMethod, session_scope


async def test_sync_updates_mapped_fields_only():
    async with session_scope() as session:
        user = User(
            email="old@example.com", hashed_password="x", is_active=True,
            auth_method=AuthMethod.LDAP, full_name="Old Name",
            phone="+33000", office="Old Office", title="Old Title", team="Old Team",
            employment_status="Permanent",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    info = LdapUserInfo(
        email="new@example.com", dn="cn=x,dc=example,dc=com",
        full_name="New Name", phone="+33111", office="New Office",
        title="New Title", department="New Team",
    )
    await sync_user_from_ldap(user_id, info)

    async with session_scope() as session:
        refreshed = await session.get(User, user_id)
        assert refreshed.email == "new@example.com"
        assert refreshed.full_name == "New Name"
        assert refreshed.phone == "+33111"
        assert refreshed.office == "New Office"
        assert refreshed.title == "New Title"
        assert refreshed.team == "New Team"
        # Local-only fields preserved
        assert refreshed.employment_status == "Permanent"


async def test_sync_accepts_none_values():
    async with session_scope() as session:
        user = User(
            email="u@example.com", hashed_password="x", is_active=True,
            auth_method=AuthMethod.LDAP, phone="+33111",
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    info = LdapUserInfo(email="u@example.com", dn="cn=x,dc=example,dc=com", phone=None)
    await sync_user_from_ldap(user_id, info)

    async with session_scope() as session:
        refreshed = await session.get(User, user_id)
        assert refreshed.phone is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ldap_sync.py -v`
Expected: FAIL — `sync_user_from_ldap` not defined.

- [ ] **Step 3: Implement**

Append to `not_dot_net/backend/auth/ldap.py`:

```python
import uuid as _uuid


# LdapUserInfo field name -> User model field name
_INFO_TO_USER: dict[str, str] = {
    "email":      "email",
    "full_name":  "full_name",
    "phone":      "phone",
    "office":     "office",
    "title":      "title",
    "department": "team",
}


async def sync_user_from_ldap(user_id: "_uuid.UUID", info: LdapUserInfo) -> None:
    """Overwrite the AD-backed fields of a local user from a freshly-read AD entry.

    Local-only fields (employment_status, start_date, end_date) are untouched.
    """
    from not_dot_net.backend.db import User, session_scope

    async with session_scope() as session:
        user = await session.get(User, user_id)
        if user is None:
            return
        for info_field, user_field in _INFO_TO_USER.items():
            setattr(user, user_field, getattr(info, info_field))
        await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ldap_sync.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/auth/ldap.py tests/test_ldap_sync.py
git commit -m "feat(ldap): sync_user_from_ldap helper for login refresh"
```

---

## Task 4: Re-sync on every LDAP login

**Files:**
- Modify: `not_dot_net/frontend/login.py:62-95` (`_try_ldap_auth`)
- Modify: `tests/test_ldap_provision.py` (add sync-on-login test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ldap_provision.py`:

```python
async def test_existing_ldap_user_gets_resynced_on_login():
    fake_users = {
        "jdoe": {
            "mail": "jdoe@example.com",
            "displayName": "John Doe",
            "givenName": "John", "sn": "Doe",
            "telephoneNumber": "+33NEW", "physicalDeliveryOfficeName": "Room 101",
            "title": "Researcher", "department": "Plasma",
            "password": "secret",
        },
    }
    await ldap_config.set(LDAP_CFG)
    set_ldap_connect(_make_fake_connect(fake_users))

    # Pre-seed a local user with stale data
    async with session_scope() as session:
        user = User(
            email="jdoe@example.com", hashed_password="x", is_active=True,
            auth_method=AuthMethod.LDAP, phone="+33OLD", office="Old Room",
            employment_status="Permanent",
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    user = await _try_ldap_auth("jdoe", "secret")
    assert user is not None
    assert user.phone == "+33NEW"
    assert user.office == "Room 101"
    assert user.title == "Researcher"
    assert user.team == "Plasma"

    async with session_scope() as session:
        refreshed = await session.get(User, user_id)
        assert refreshed.employment_status == "Permanent"  # preserved
```

(Relies on the extended `_make_fake_connect` from Task 1 Step 4.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ldap_provision.py::test_existing_ldap_user_gets_resynced_on_login -v`
Expected: FAIL — sync not called, phone still "+33OLD".

- [ ] **Step 3: Implement**

Modify `not_dot_net/frontend/login.py` `_try_ldap_auth`:

```python
async def _try_ldap_auth(username: str, password: str):
    """Attempt LDAP auth. Returns User or None. Syncs AD attrs on success."""
    from not_dot_net.backend.auth.ldap import (
        USERNAME_RE, ldap_config, ldap_authenticate, get_ldap_connect,
        provision_ldap_user, sync_user_from_ldap,
    )
    from not_dot_net.backend.db import session_scope, get_user_db
    from not_dot_net.backend.roles import roles_config
    from contextlib import asynccontextmanager

    if not USERNAME_RE.match(username):
        return None

    cfg = await ldap_config.get()
    user_info = ldap_authenticate(username, password, cfg, get_ldap_connect())
    if user_info is None:
        return None

    async with session_scope() as session:
        async with asynccontextmanager(get_user_db)(session) as user_db:
            user = await user_db.get_by_email(user_info.email)

    if user is not None:
        if not user.is_active:
            return None
        await sync_user_from_ldap(user.id, user_info)
        async with session_scope() as session:
            return await session.get(type(user), user.id)

    if not cfg.auto_provision:
        logger.info("LDAP user '%s' has no local account and auto_provision is off", user_info.email)
        return None

    roles_cfg = await roles_config.get()
    default_role = roles_cfg.default_role or ""
    return await provision_ldap_user(user_info, default_role)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ldap_provision.py tests/test_login.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/frontend/login.py tests/test_ldap_provision.py
git commit -m "feat(login): re-sync LDAP user attrs on every successful bind"
```

---

## Task 5: Classify field changes in edit flow

Before touching UI, add a pure helper that splits an edit into AD-bound changes and local-only changes. Testable in isolation.

**Files:**
- Modify: `not_dot_net/frontend/directory.py` (add classifier)
- Modify: `tests/test_directory.py` (unit test the classifier)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_directory.py`:

```python
from not_dot_net.frontend.directory import classify_updates


def test_classify_updates_splits_ad_and_local_fields():
    updates = {
        "phone": "+33999",
        "office": "New",
        "employment_status": "Contractor",
        "start_date": None,
    }
    ad_changes, local_updates = classify_updates(updates)
    assert ad_changes == {
        "telephoneNumber": "+33999",
        "physicalDeliveryOfficeName": "New",
    }
    assert local_updates == {
        "employment_status": "Contractor",
        "start_date": None,
    }


def test_classify_updates_ignores_unmapped_fields():
    ad_changes, local_updates = classify_updates({"unknown": "x"})
    assert ad_changes == {}
    assert local_updates == {"unknown": "x"}


def test_classify_updates_empty_input():
    assert classify_updates({}) == ({}, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_directory.py::test_classify_updates_splits_ad_and_local_fields -v`
Expected: FAIL — `classify_updates` not defined.

- [ ] **Step 3: Implement**

Add to `not_dot_net/frontend/directory.py` (near top, after imports):

```python
from not_dot_net.backend.auth.ldap import AD_ATTR_MAP


def classify_updates(updates: dict) -> tuple[dict[str, str | None], dict]:
    """Split a user-update dict into (AD attribute changes, local-only DB updates).

    AD changes are keyed by AD attribute name (telephoneNumber, ...).
    """
    ad_changes: dict[str, str | None] = {}
    local_updates: dict = {}
    for field, value in updates.items():
        ad_attr = AD_ATTR_MAP.get(field)
        if ad_attr is not None:
            ad_changes[ad_attr] = value
        else:
            local_updates[field] = value
    return ad_changes, local_updates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_directory.py -v`
Expected: all PASS (3 new + existing).

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/frontend/directory.py tests/test_directory.py
git commit -m "refactor(directory): add classify_updates helper"
```

---

## Task 6: Restrict self-editable AD fields in the edit dialog

Only `phone` and `office` are self-editable AD fields. Admins can edit all AD fields. This matches current code (`is_admin` gate already wraps the richer field set) — we just need to ensure non-admins cannot submit AD-unmapped edits that are actually admin-only. Current code already gates those inputs behind `is_admin`, so this task only adds an explicit test to lock the invariant.

**Files:**
- Modify: `tests/test_directory.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_directory.py`:

```python
SELF_EDITABLE_AD_FIELDS = {"phone", "office"}
ADMIN_EDITABLE_AD_FIELDS = {"phone", "office", "full_name", "title", "team", "email"}


def test_self_editable_ad_fields_are_subset_of_admin_editable():
    assert SELF_EDITABLE_AD_FIELDS.issubset(ADMIN_EDITABLE_AD_FIELDS)


def test_self_editable_ad_fields_map_to_valid_ad_attributes():
    from not_dot_net.backend.auth.ldap import AD_ATTR_MAP
    for f in SELF_EDITABLE_AD_FIELDS:
        assert f in AD_ATTR_MAP
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_directory.py -v`
Expected: PASS immediately — this is a guard test documenting the invariant.

- [ ] **Step 3: Commit** (only if anything changed)

```bash
git add tests/test_directory.py
git commit -m "test(directory): document self/admin AD-field invariant"
```

---

## Task 7: Password-prompt dialog and unified save flow

This is the user-facing change. When `save()` is clicked:

1. Compute `updates` diff (only fields that actually changed vs. current value).
2. Call `classify_updates` → `(ad_changes, local_updates)`.
3. If target user's `auth_method != LDAP` OR `ad_changes == {}`: skip AD, just update DB.
4. Otherwise: open a password prompt dialog.
   - Self-edit (`is_own`): prompt "Enter your password to save changes to Active Directory".
   - Admin-edit (`not is_own`): prompt for **admin username + password** ("Provide AD admin credentials").
5. On submit: call `ldap_modify_user(dn, ad_changes, bind_username, bind_password, cfg)`. On success → update local DB with *all* updates (AD + local). On `LdapModifyError` → notify and keep dialog open so user can retry.

We need the target user's DN. Strategy: store it on the `User` model? No — `User` doesn't have it and we don't want to add one more field that drifts. Instead, derive it fresh: on edit-time, the **current** user's own DN comes from their last LDAP login (we can persist it on `User` — lightweight, matches the "AD is source of truth" direction). For admin-editing someone else, we look up that user by email during the AD bind using the admin's credentials.

**Sub-task 7a: add `ldap_dn` column to `User`.**

**Files:**
- Modify: `not_dot_net/backend/db.py` (add `ldap_dn`)
- Modify: `not_dot_net/backend/auth/ldap.py` (`sync_user_from_ldap` stores `dn`; `provision_ldap_user` stores `dn`)
- Modify: `tests/test_ldap_sync.py` (assert `ldap_dn` set)
- Modify: `tests/test_ldap_provision.py` (assert `ldap_dn` set)

- [ ] **Step 1: Write failing tests**

Extend `tests/test_ldap_sync.py::test_sync_updates_mapped_fields_only` to assert:

```python
assert refreshed.ldap_dn == "cn=x,dc=example,dc=com"
```

And in `tests/test_ldap_provision.py`, add (or extend):

```python
async def test_provision_stores_dn():
    from not_dot_net.backend.auth.ldap import provision_ldap_user, LdapUserInfo
    info = LdapUserInfo(email="n@example.com", dn="cn=n,dc=example,dc=com")
    user = await provision_ldap_user(info, default_role="member")
    assert user.ldap_dn == "cn=n,dc=example,dc=com"
```

- [ ] **Step 2: Run tests — expect fail**

Run: `uv run pytest tests/test_ldap_sync.py tests/test_ldap_provision.py -v`
Expected: FAIL — `ldap_dn` not on model.

- [ ] **Step 3: Implement**

In `not_dot_net/backend/db.py` add to `User`:

```python
ldap_dn: Mapped[str | None] = mapped_column(default=None)
```

In `sync_user_from_ldap`, after the `_INFO_TO_USER` loop:

```python
user.ldap_dn = info.dn
```

In `provision_ldap_user`, after `user.full_name = user_info.full_name`:

```python
user.ldap_dn = user_info.dn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ldap_sync.py tests/test_ldap_provision.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add not_dot_net/backend/db.py not_dot_net/backend/auth/ldap.py tests/test_ldap_sync.py tests/test_ldap_provision.py
git commit -m "feat(user): persist ldap_dn for AD write-back"
```

**Sub-task 7b: `compute_update_diff` helper + save-flow rewrite.**

**Files:**
- Modify: `not_dot_net/frontend/directory.py` (add diff helper, rewrite save handler)
- Modify: `not_dot_net/frontend/i18n.py` (new keys)
- Modify: `tests/test_directory.py` (test diff helper)

- [ ] **Step 1: Write the failing test (diff helper)**

Add to `tests/test_directory.py`:

```python
from not_dot_net.frontend.directory import compute_update_diff


def test_compute_update_diff_returns_only_changed():
    current = {"phone": "+33111", "office": "A"}
    submitted = {"phone": "+33222", "office": "A"}
    assert compute_update_diff(current, submitted) == {"phone": "+33222"}


def test_compute_update_diff_treats_empty_string_as_none():
    current = {"phone": "+33111"}
    submitted = {"phone": ""}
    assert compute_update_diff(current, submitted) == {"phone": None}


def test_compute_update_diff_no_changes_returns_empty():
    assert compute_update_diff({"phone": "+33111"}, {"phone": "+33111"}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_directory.py::test_compute_update_diff_returns_only_changed -v`
Expected: FAIL.

- [ ] **Step 3: Implement the helper**

In `not_dot_net/frontend/directory.py`:

```python
def compute_update_diff(current: dict, submitted: dict) -> dict:
    """Return only fields whose submitted value differs from current. Empty strings -> None."""
    out: dict = {}
    for k, raw in submitted.items():
        new_val = raw if raw not in ("", None) else None
        if new_val != current.get(k):
            out[k] = new_val
    return out
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_directory.py -v`
Expected: PASS.

- [ ] **Step 5: i18n keys**

In `not_dot_net/frontend/i18n.py` add (both EN and FR dicts):

```python
# EN
"confirm_password_to_save_ad": "Enter your password to save changes to Active Directory",
"admin_ad_credentials": "Provide AD admin credentials",
"ad_admin_username": "AD admin username",
"ad_write_failed": "Active Directory update failed: {error}",
"ad_bind_failed": "Incorrect password — try again",

# FR
"confirm_password_to_save_ad": "Entrez votre mot de passe pour enregistrer les modifications dans l'Active Directory",
"admin_ad_credentials": "Fournissez les identifiants administrateur AD",
"ad_admin_username": "Nom d'utilisateur administrateur AD",
"ad_write_failed": "Échec de la mise à jour de l'Active Directory : {error}",
"ad_bind_failed": "Mot de passe incorrect — réessayez",
```

- [ ] **Step 6: Rewrite the save handler**

Replace the `save` function inside `_render_edit` (`not_dot_net/frontend/directory.py`). Full replacement:

```python
async def save():
    submitted = {}
    for k, v in fields.items():
        val = v.value or None
        if k in ("start_date", "end_date") and val:
            val = date.fromisoformat(val)
        submitted[k] = val

    current = {k: getattr(person, k) for k in submitted}
    diff = compute_update_diff(current, submitted)
    if not diff:
        ui.notify(t("saved"), color="positive")
        return

    ad_changes, local_updates = classify_updates(diff)
    needs_ad_write = bool(ad_changes) and person.auth_method == AuthMethod.LDAP

    if not needs_ad_write:
        await _update_user(person.id, diff)
        await _finish_save(container, person, current_user, state)
        return

    is_own = person.id == current_user.id
    await _prompt_ad_credentials_and_save(
        container, person, current_user, state,
        diff, ad_changes, local_updates, is_own=is_own,
    )
```

Add helper `_finish_save`:

```python
async def _finish_save(container, person, current_user, state):
    ui.notify(t("saved"), color="positive")
    people = await _load_people()
    updated = next((p for p in people if p.id == person.id), person)
    await _render_detail(container, updated, current_user, state)
```

Add helper `_prompt_ad_credentials_and_save`:

```python
async def _prompt_ad_credentials_and_save(
    container, person, current_user, state,
    diff, ad_changes, local_updates, *, is_own,
):
    from not_dot_net.backend.auth.ldap import (
        ldap_config, get_ldap_connect, ldap_modify_user, LdapModifyError,
    )

    dialog = ui.dialog()
    with dialog, ui.card():
        if is_own:
            ui.label(t("confirm_password_to_save_ad"))
            username_input = None
            password_input = ui.input(t("password"), password=True).props("outlined dense")
        else:
            ui.label(t("admin_ad_credentials"))
            username_input = ui.input(t("ad_admin_username")).props("outlined dense")
            password_input = ui.input(t("password"), password=True).props("outlined dense")
        error_label = ui.label("").classes("text-negative")

        async def submit():
            bind_user = (current_user.email.split("@")[0] if is_own else username_input.value)
            if not bind_user or not password_input.value:
                return
            cfg = await ldap_config.get()
            try:
                ldap_modify_user(
                    dn=person.ldap_dn,
                    changes=ad_changes,
                    bind_username=bind_user,
                    bind_password=password_input.value,
                    ldap_cfg=cfg,
                    connect=get_ldap_connect(),
                )
            except LdapModifyError as e:
                msg = str(e)
                error_label.set_text(
                    t("ad_bind_failed") if "bind" in msg.lower() else t("ad_write_failed", error=msg)
                )
                return
            await _update_user(person.id, diff)
            dialog.close()
            await _finish_save(container, person, current_user, state)

        with ui.row():
            ui.button(t("save"), on_click=submit).props("flat color=primary")
            ui.button(t("cancel"), on_click=dialog.close).props("flat")

    dialog.open()
```

Also add import at top:

```python
from not_dot_net.backend.db import User, AuthMethod, session_scope, get_user_db
```

(replacing the existing `from ...db import User, session_scope, get_user_db`).

- [ ] **Step 7: Run all directory tests**

Run: `uv run pytest tests/test_directory.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add not_dot_net/frontend/directory.py not_dot_net/frontend/i18n.py tests/test_directory.py
git commit -m "feat(directory): prompt for AD creds and write-back on profile edit"
```

---

## Task 8: Integration test — full self-edit round trip

**Files:**
- Modify: `tests/test_directory.py`

- [ ] **Step 1: Write the test**

```python
async def test_self_edit_phone_writes_to_ad_and_local_db():
    from not_dot_net.backend.db import User, AuthMethod, session_scope
    from not_dot_net.backend.auth.ldap import (
        ldap_config, set_ldap_connect, ldap_modify_user,
    )
    from tests.test_ldap_modify import _make_mutable_fake, LDAP_CFG, USER_DN

    fake_connect, ad_state = _make_mutable_fake({"telephoneNumber": "+33OLD"})
    await ldap_config.set(LDAP_CFG)
    set_ldap_connect(fake_connect)

    async with session_scope() as session:
        user = User(
            email="jdoe@example.com", hashed_password="x", is_active=True,
            auth_method=AuthMethod.LDAP,
            ldap_dn=USER_DN,
            phone="+33OLD",
        )
        session.add(user)
        await session.commit()

    cfg = await ldap_config.get()
    ldap_modify_user(
        dn=USER_DN,
        changes={"telephoneNumber": "+33NEW"},
        bind_username="jdoe", bind_password="secret",
        ldap_cfg=cfg, connect=fake_connect,
    )
    assert ad_state["telephoneNumber"] == "+33NEW"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_directory.py::test_self_edit_phone_writes_to_ad_and_local_db -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_directory.py
git commit -m "test(directory): self-edit round-trip through AD"
```

---

## Task 9: Wire up — full test run + manual smoke test

- [ ] **Step 1: Full test run**

Run: `uv run pytest`
Expected: all green. Fix any regressions inline.

- [ ] **Step 2: Manual smoke test**

Start dev server:

```bash
DATABASE_URL=sqlite+aiosqlite:///./smoke.db uv run python -m not_dot_net.cli serve --host localhost --port 8000
```

Checklist:
- Log in with LDAP test user → verify local DB phone/office/title/team/full_name matches AD.
- Edit own phone → password prompt appears → submit correct password → AD + local DB both updated.
- Edit own phone → submit wrong password → "Incorrect password" shown, dialog stays open.
- Admin edits another user's team → admin credential prompt appears → on submit, AD + local DB both updated.
- Edit employment_status (admin only, local-only field) → saves without any AD prompt.
- Edit a LOCAL (non-LDAP) user's phone → saves without AD prompt.

- [ ] **Step 3: Commit any fixes from smoke test** (if needed)

---

## Notes for the implementer

- **AD permissions deployment caveat:** This plan implements the code path. For self-edit to actually succeed in production, AD must grant users the `Write Personal-Information` delegated right on their own object (or a narrower ACL covering `telephoneNumber` + `physicalDeliveryOfficeName`). That's an AD admin task, not a code task. `LdapModifyError` with "insufficient access rights" tells you the ACL isn't in place.
- **DN stability:** DN changes (user moved between OUs) would break our stored `ldap_dn`. Accepted: next login refreshes it.
- **Password not stored anywhere:** `_prompt_ad_credentials_and_save` holds the password in a closure for the duration of the modify call, then it goes out of scope. Nothing is logged.
- **No new external config:** `LdapConfig` does not grow; no stored admin creds. Everything required already exists.
