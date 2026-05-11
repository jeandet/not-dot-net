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



class KeyedChipEditor:
    """Editor for `dict[str, list[str]]`.

    Renders a vertical stack of rows: `[key input | chip_list_editor | trash]`,
    plus an "Add" row at the bottom. The current value is exposed via the
    `value` property.
    """

    def __init__(self, value: dict[str, list[str]], *, key_label: str = "Key"):
        self._key_label = key_label
        self._rows: dict[str, dict] = {}
        self._container = ui.column().classes("w-full gap-2")
        with self._container:
            for k, vs in (value or {}).items():
                self._add_row(k, list(vs))
            self._add_button = ui.button("+ Add", on_click=self._on_add).props("flat dense color=primary")

    @property
    def value(self) -> dict[str, list[str]]:
        return {row["key_input"].value: list(row["chip"].value) for row in self._rows.values()}

    def add_key(self, key: str, values: list[str] | None = None) -> None:
        with self._container:
            self._add_row(key, values or [])
            self._add_button.move(self._container)

    def remove_key(self, key: str) -> None:
        row = self._rows.pop(key, None)
        if row:
            row["container"].delete()

    def set_values(self, key: str, values: list[str]) -> None:
        row = self._rows.get(key)
        if row:
            row["chip"].value = list(values)

    def _add_row(self, key: str, values: list[str]):
        row_container = ui.row().classes("w-full items-center gap-2 no-wrap")
        with row_container:
            key_input = ui.input(label=self._key_label, value=key).props("dense outlined stack-label").classes("w-40")
            chip = chip_list_editor(values)
            ui.button(icon="delete", on_click=lambda k=key: self.remove_key(k)).props("flat dense round color=negative")
        self._rows[key] = {"container": row_container, "key_input": key_input, "chip": chip}

    def _on_add(self):
        new_key = f"key_{len(self._rows) + 1}"
        self.add_key(new_key, [])

    def tooltip(self, text: str) -> "KeyedChipEditor":
        self._container.tooltip(text)
        return self


def keyed_chip_editor(value: dict[str, list[str]], *, key_label: str = "Key") -> KeyedChipEditor:
    return KeyedChipEditor(value, key_label=key_label)
