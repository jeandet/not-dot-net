"""Tests for custom page CRUD."""

import pytest

from not_dot_net.backend.page_models import Page


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
