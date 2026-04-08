"""Tests for custom page CRUD."""

import pytest

from not_dot_net.backend.page_models import Page
from not_dot_net.backend.page_service import (
    MANAGE_PAGES,
    create_page,
    delete_page,
    get_page,
    list_pages,
    update_page,
)


async def test_page_model_exists():
    p = Page(
        title="Hello",
        slug="hello",
        content="# Hello\nWorld",
        author_id=None,
    )
    assert p.title == "Hello"
    assert p.slug == "hello"
    assert p.published is False
    assert p.sort_order == 0


async def test_create_and_get_page():
    page = await create_page(
        title="Welcome", slug="welcome", content="# Welcome\nHello!", author_id=None,
    )
    assert page.id is not None
    assert page.slug == "welcome"
    assert page.published is False

    fetched = await get_page("welcome")
    assert fetched is not None
    assert fetched.title == "Welcome"


async def test_get_page_not_found():
    result = await get_page("nonexistent")
    assert result is None


async def test_list_pages_published_only():
    await create_page(title="Draft", slug="draft", content="x", author_id=None)
    await create_page(
        title="Public", slug="public", content="y", author_id=None, published=True,
    )
    published = await list_pages(published_only=True)
    assert all(p.published for p in published)
    assert any(p.slug == "public" for p in published)
    assert not any(p.slug == "draft" for p in published)

    all_pages = await list_pages(published_only=False)
    slugs = [p.slug for p in all_pages]
    assert "draft" in slugs
    assert "public" in slugs


async def test_list_pages_sort_order():
    await create_page(title="B", slug="b-page", content="", author_id=None, sort_order=2, published=True)
    await create_page(title="A", slug="a-page", content="", author_id=None, sort_order=1, published=True)
    pages = await list_pages(published_only=True)
    slugs = [p.slug for p in pages]
    assert slugs.index("a-page") < slugs.index("b-page")


async def test_update_page():
    page = await create_page(title="Old", slug="upd", content="old", author_id=None)
    updated = await update_page(page.id, title="New", content="new")
    assert updated.title == "New"
    assert updated.content == "new"
    assert updated.slug == "upd"


async def test_delete_page():
    page = await create_page(title="Bye", slug="bye", content="", author_id=None)
    await delete_page(page.id)
    assert await get_page("bye") is None


async def test_create_duplicate_slug_raises():
    await create_page(title="One", slug="dup", content="", author_id=None)
    with pytest.raises(ValueError, match="slug"):
        await create_page(title="Two", slug="dup", content="", author_id=None)


async def test_manage_pages_permission_registered():
    from not_dot_net.backend.permissions import get_permissions
    assert MANAGE_PAGES in get_permissions()
