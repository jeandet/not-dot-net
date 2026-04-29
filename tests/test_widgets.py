"""Tests for reusable settings widgets."""

import pytest
from nicegui import ui
from nicegui.testing import User

from not_dot_net.frontend.widgets import chip_list_editor


async def test_chip_list_editor_initial_value(user: User):
    @ui.page("/_w1")
    def _page():
        chip_list_editor(["a", "b", "c"])
    await user.open("/_w1")
    select = user.find(kind=ui.select).elements.pop()
    assert list(select.value) == ["a", "b", "c"]


async def test_chip_list_editor_returns_list_type(user: User):
    @ui.page("/_w2")
    def _page():
        w = chip_list_editor([])
        assert isinstance(w.value, list)
    await user.open("/_w2")


async def test_chip_list_editor_writes_back_list(user: User):
    captured = {}

    @ui.page("/_w3")
    def _page():
        w = chip_list_editor(["x"])
        captured["w"] = w
    await user.open("/_w3")
    captured["w"].value = ["x", "y"]
    assert captured["w"].value == ["x", "y"]
