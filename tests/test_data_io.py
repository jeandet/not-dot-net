"""Tests for import/export of pages and resources."""

import uuid

from not_dot_net.backend.data_io import (
    export_all, export_pages, export_resources,
    import_all, import_pages, import_resources,
)
from not_dot_net.backend.page_models import Page
from not_dot_net.backend.booking_models import Resource
from not_dot_net.backend.db import session_scope, User


async def _create_user(email: str) -> User:
    async with session_scope() as session:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password="x",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _seed_page(title="Test", slug="test", content="# Hello", published=True):
    async with session_scope() as session:
        p = Page(title=title, slug=slug, content=content, published=published)
        session.add(p)
        await session.commit()


async def _seed_resource(name="PC-01", resource_type="desktop"):
    async with session_scope() as session:
        r = Resource(name=name, resource_type=resource_type)
        session.add(r)
        await session.commit()


async def test_export_pages():
    await _seed_page()
    pages = await export_pages()
    assert len(pages) == 1
    assert pages[0]["slug"] == "test"
    assert "id" not in pages[0]


async def test_export_resources():
    await _seed_resource()
    resources = await export_resources()
    assert len(resources) == 1
    assert resources[0]["name"] == "PC-01"
    assert "id" not in resources[0]


async def test_export_all_structure():
    await _seed_page()
    await _seed_resource()
    data = await export_all()
    assert data["version"] == 1
    assert "exported_at" in data
    assert len(data["pages"]) == 1
    assert len(data["resources"]) == 1


async def test_import_pages_creates():
    result = await import_pages([
        {"title": "New", "slug": "new", "content": "body", "published": True},
    ])
    assert result == {"created": 1, "updated": 0, "skipped": 0}
    pages = await export_pages()
    assert len(pages) == 1
    assert pages[0]["slug"] == "new"


async def test_import_pages_skips_existing():
    await _seed_page(slug="existing")
    result = await import_pages([
        {"title": "Changed", "slug": "existing", "content": "new body"},
    ])
    assert result == {"created": 0, "updated": 0, "skipped": 1}


async def test_import_pages_replaces_existing():
    await _seed_page(title="Old", slug="replace-me", content="old")
    result = await import_pages([
        {"title": "New Title", "slug": "replace-me", "content": "new"},
    ], replace=True)
    assert result == {"created": 0, "updated": 1, "skipped": 0}
    pages = await export_pages()
    assert pages[0]["title"] == "New Title"
    assert pages[0]["content"] == "new"


async def test_import_pages_skips_empty_slug():
    result = await import_pages([{"title": "Bad", "slug": "", "content": "x"}])
    assert result["skipped"] == 1


async def test_import_resources_creates():
    result = await import_resources([
        {"name": "Laptop-01", "resource_type": "laptop", "location": "Room 1"},
    ])
    assert result == {"created": 1, "updated": 0, "skipped": 0}


async def test_import_resources_skips_existing():
    await _seed_resource(name="PC-01")
    result = await import_resources([{"name": "PC-01", "resource_type": "laptop"}])
    assert result == {"created": 0, "updated": 0, "skipped": 1}


async def test_import_resources_replaces_existing():
    await _seed_resource(name="PC-02", resource_type="desktop")
    result = await import_resources([
        {"name": "PC-02", "resource_type": "laptop", "location": "New Room"},
    ], replace=True)
    assert result == {"created": 0, "updated": 1, "skipped": 0}
    resources = await export_resources()
    r = next(r for r in resources if r["name"] == "PC-02")
    assert r["resource_type"] == "laptop"
    assert r["location"] == "New Room"


async def test_import_all_roundtrip():
    await _seed_page(title="P1", slug="p1")
    await _seed_resource(name="R1")
    exported = await export_all()
    # Clear DB
    async with session_scope() as session:
        from sqlalchemy import delete
        await session.execute(delete(Page))
        await session.execute(delete(Resource))
        await session.commit()
    result = await import_all(exported)
    assert result["pages"]["created"] == 1
    assert result["resources"]["created"] == 1


async def test_export_includes_tenures():
    from not_dot_net.backend.data_io import export_all
    from not_dot_net.backend.tenure_service import add_tenure
    from datetime import date

    user = await _create_user("tenure-export@test.com")
    await add_tenure(
        user_id=user.id, status="PhD", employer="CNRS",
        start_date=date(2025, 9, 1),
    )
    data = await export_all()
    assert "tenures" in data
    assert len(data["tenures"]) == 1
    assert data["tenures"][0]["status"] == "PhD"
    assert data["tenures"][0]["employer"] == "CNRS"


async def test_import_tenures():
    from not_dot_net.backend.data_io import import_all
    from not_dot_net.backend.tenure_service import list_tenures

    user = await _create_user("import-tenure@test.com")
    data = {
        "tenures": [
            {
                "user_email": "import-tenure@test.com",
                "status": "Intern",
                "employer": "Polytechnique",
                "start_date": "2025-03-01",
                "end_date": "2025-08-31",
            }
        ],
    }
    result = await import_all(data)
    assert result["tenures"]["created"] == 1
    tenures = await list_tenures(user.id)
    assert len(tenures) == 1
    assert tenures[0].employer == "Polytechnique"
