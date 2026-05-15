import uuid
import pytest
from sqlalchemy import select

from not_dot_net.backend.db import session_scope, User, AuthMethod
from not_dot_net.backend.uid_allocator import (
    allocate_uid, UidAllocation, UidRangeExhausted,
)
from not_dot_net.backend.ad_account_config import ad_account_config


async def _make_user(email: str = "u@example.com") -> uuid.UUID:
    async with session_scope() as session:
        u = User(
            email=email,
            full_name="U",
            hashed_password="x",
            auth_method=AuthMethod.LOCAL,
            role="",
            is_active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u.id


@pytest.mark.asyncio
async def test_allocate_uid_empty_returns_uid_min():
    uid_user = await _make_user()
    uid = await allocate_uid(uid_user, "alpha")
    assert uid == 10000


@pytest.mark.asyncio
async def test_allocate_uid_fills_smallest_gap():
    uid_user = await _make_user()
    async with session_scope() as session:
        session.add(UidAllocation(uid=10000, source="allocated", sam_account="a"))
        session.add(UidAllocation(uid=10002, source="allocated", sam_account="b"))
        await session.commit()
    uid = await allocate_uid(uid_user, "c")
    assert uid == 10001


@pytest.mark.asyncio
async def test_allocate_uid_contiguous_returns_max_plus_one():
    uid_user = await _make_user()
    async with session_scope() as session:
        for n in (10000, 10001, 10002):
            session.add(UidAllocation(uid=n, source="allocated", sam_account=f"u{n}"))
        await session.commit()
    uid = await allocate_uid(uid_user, "z")
    assert uid == 10003


@pytest.mark.asyncio
async def test_allocate_uid_range_exhausted_raises():
    uid_user = await _make_user()
    cfg = await ad_account_config.get()
    await ad_account_config.set(cfg.model_copy(update={"uid_min": 10, "uid_max": 11}))
    async with session_scope() as session:
        session.add(UidAllocation(uid=10, source="allocated", sam_account="a"))
        session.add(UidAllocation(uid=11, source="allocated", sam_account="b"))
        await session.commit()
    with pytest.raises(UidRangeExhausted):
        await allocate_uid(uid_user, "c")


@pytest.mark.asyncio
async def test_allocate_uid_writes_row_with_metadata():
    uid_user = await _make_user("metadata@example.com")
    uid = await allocate_uid(uid_user, "metaman")
    async with session_scope() as session:
        row = (await session.execute(select(UidAllocation).where(UidAllocation.uid == uid))).scalar_one()
    assert row.source == "allocated"
    assert row.user_id == uid_user
    assert row.sam_account == "metaman"


@pytest.mark.asyncio
async def test_allocate_uid_writes_audit_event():
    from not_dot_net.backend.audit import list_audit_events
    uid_user = await _make_user("audit@example.com")
    uid = await allocate_uid(uid_user, "audited")
    events = await list_audit_events(category="ad", action="allocate_uid")
    assert any(ev.target_id == str(uid_user) and str(uid) in str(ev.detail) for ev in events)


class _FakeEntry:
    def __init__(self, uid_number, sam):
        from types import SimpleNamespace
        self.uidNumber = SimpleNamespace(value=uid_number)
        self.sAMAccountName = SimpleNamespace(value=sam)
        self.entry_dn = f"CN={sam},OU=Users,DC=example,DC=com"


class _FakeConn:
    def __init__(self, entries):
        self.entries = entries
        self.bound = True

    def search(self, *args, **kwargs):
        return True

    def unbind(self):
        self.bound = False


def _fake_connect_factory(entries):
    def _connect(cfg, username, password):
        return _FakeConn(entries)
    return _connect


@pytest.mark.asyncio
async def test_seed_from_ad_inserts_seeded_rows(monkeypatch):
    from not_dot_net.backend import uid_allocator
    from not_dot_net.backend.uid_allocator import seed_from_ad

    entries = [_FakeEntry(20000, "alice"), _FakeEntry(20001, "bob")]
    monkeypatch.setattr(
        uid_allocator,
        "_search_ad_uids",
        lambda cfg, user, pw: entries,
    )
    result = await seed_from_ad("admin", "secret")
    assert result.seeded == 2
    assert result.skipped == 0

    async with session_scope() as session:
        rows = (await session.execute(select(UidAllocation))).scalars().all()
    assert {r.uid for r in rows} == {20000, 20001}
    assert all(r.source == "seeded_from_ad" for r in rows)


@pytest.mark.asyncio
async def test_seed_from_ad_is_idempotent(monkeypatch):
    from not_dot_net.backend import uid_allocator
    from not_dot_net.backend.uid_allocator import seed_from_ad

    entries = [_FakeEntry(30000, "x"), _FakeEntry(30001, "y")]
    monkeypatch.setattr(
        uid_allocator,
        "_search_ad_uids",
        lambda cfg, user, pw: entries,
    )
    first = await seed_from_ad("admin", "secret")
    second = await seed_from_ad("admin", "secret")
    assert first.seeded == 2 and first.skipped == 0
    assert second.seeded == 0 and second.skipped == 2


class _FakePagedConn:
    """Fake ldap3 connection that hands out one page of entries per search() call."""

    PAGING_OID = "1.2.840.113556.1.4.319"

    def __init__(self, pages):
        self._pages = pages
        self._call = 0
        self.entries: list = []
        self.result: dict = {"controls": {}}
        self.bound = True

    def search(self, *args, **kwargs):
        self.entries = self._pages[self._call]
        more = self._call + 1 < len(self._pages)
        cookie = b"next-page-cookie" if more else b""
        self.result = {"controls": {self.PAGING_OID: {"value": {"cookie": cookie}}}}
        self._call += 1
        return True

    def unbind(self):
        self.bound = False


@pytest.mark.asyncio
async def test_search_ad_uids_walks_all_pages(monkeypatch):
    """_search_ad_uids must follow the paging cookie, not stop after one page."""
    from not_dot_net.backend import uid_allocator
    from not_dot_net.backend.auth import ldap as ldap_module

    page1 = [_FakeEntry(40000 + i, f"u{i}") for i in range(500)]
    page2 = [_FakeEntry(40500 + i, f"v{i}") for i in range(3)]
    fake = _FakePagedConn([page1, page2])

    monkeypatch.setattr(ldap_module, "_ldap_bind", lambda *a, **kw: fake)
    monkeypatch.setattr(ldap_module, "get_ldap_connect", lambda: (lambda *a, **kw: fake))

    class _DummyCfg:
        base_dn = "dc=example,dc=com"

    entries = uid_allocator._search_ad_uids(_DummyCfg(), "admin", "pw")
    assert len(entries) == 503


@pytest.mark.asyncio
async def test_list_allocations_returns_views_desc_by_acquired():
    from not_dot_net.backend.uid_allocator import list_allocations
    uid_user = await _make_user("list@example.com")
    await allocate_uid(uid_user, "first")
    await allocate_uid(uid_user, "second")
    views = await list_allocations(limit=10)
    assert len(views) >= 2
    # Most recent first
    assert views[0].acquired_at >= views[1].acquired_at
    assert all(hasattr(v, "uid") and hasattr(v, "sam_account") for v in views)
