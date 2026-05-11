"""Tests for reusable settings widgets."""

import pytest
from nicegui import ui
from nicegui.testing import User

from not_dot_net.frontend.widgets import chip_list_editor, keyed_chip_editor


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


async def test_keyed_chip_editor_initial_value(user: User):
    captured = {}

    @ui.page("/_k1")
    def _page():
        captured["w"] = keyed_chip_editor({"Linux": ["bash"], "Windows": ["powershell"]})
    await user.open("/_k1")
    assert captured["w"].value == {"Linux": ["bash"], "Windows": ["powershell"]}


async def test_keyed_chip_editor_add_remove_key(user: User):
    captured = {}

    @ui.page("/_k2")
    def _page():
        captured["w"] = keyed_chip_editor({"a": ["1"]})
    await user.open("/_k2")
    captured["w"].add_key("b", ["2"])
    assert captured["w"].value == {"a": ["1"], "b": ["2"]}
    captured["w"].remove_key("a")
    assert captured["w"].value == {"b": ["2"]}


async def test_keyed_chip_editor_supports_tooltip(user: User):
    """admin_settings._render_form calls widget.tooltip(hint) for any field
    with a Pydantic description — KeyedChipEditor must implement it or fields
    typed dict[str, list[str]] with a description crash the settings page.
    """
    captured = {}

    @ui.page("/_kt")
    def _page():
        w = keyed_chip_editor({})
        w.tooltip("hint text")
        captured["w"] = w

    await user.open("/_kt")
    assert captured["w"] is not None


async def test_keyed_chip_editor_nested_change_propagates(user: User):
    captured = {}

    @ui.page("/_k3")
    def _page():
        captured["w"] = keyed_chip_editor({"k": ["x"]})
    await user.open("/_k3")
    captured["w"].set_values("k", ["x", "y"])
    assert captured["w"].value == {"k": ["x", "y"]}
