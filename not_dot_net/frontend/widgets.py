"""Reusable input widgets used in admin settings forms."""

from nicegui import ui


def chip_list_editor(
    value: list[str],
    *,
    label: str = "",
    suggestions: list[str] | None = None,
):
    """Chip-style multi-value text input.

    Backed by a Quasar q-select in `use-chips` + `use-input` mode with
    `new-value-mode="add-unique"`. Reads/writes a `list[str]`.
    """
    options = list(suggestions) if suggestions else []
    select = ui.select(
        options=options,
        value=list(value),
        label=label or None,
        multiple=True,
        new_value_mode="add-unique",
    ).props('use-chips use-input outlined dense stack-label hide-dropdown-icon input-debounce=0').classes("w-full")
    return select
