"""Reusable step renderer — form fields or approval UI."""

from nicegui import ui

from not_dot_net.backend.workflow_engine import get_completion_status
from not_dot_net.config import WorkflowStepConfig
from not_dot_net.frontend.i18n import t


def render_step_form(
    step: WorkflowStepConfig,
    data: dict,
    on_submit,
    on_save_draft=None,
    files: dict | None = None,
    on_file_upload=None,
):
    """Render a form step's fields. Returns dict of field name -> ui element."""
    fields = {}
    for field_cfg in step.fields:
        label = field_cfg.label or field_cfg.name
        value = data.get(field_cfg.name, "")

        if field_cfg.type == "textarea":
            fields[field_cfg.name] = ui.textarea(
                label=label, value=value
            ).props("outlined dense").classes("w-full")
        elif field_cfg.type == "date":
            with ui.input(label=label, value=value).props("outlined dense") as inp:
                with ui.menu().props("no-parent-event") as menu:
                    with ui.date(on_change=lambda e, i=inp, m=menu: _set_date(i, m, e)):
                        pass
                with inp.add_slot("append"):
                    ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
            fields[field_cfg.name] = inp
        elif field_cfg.type == "select":
            options = _resolve_options(field_cfg.options_key)
            fields[field_cfg.name] = ui.select(
                label=label, options=options, value=value or None
            ).props("outlined dense").classes("w-full")
        elif field_cfg.type == "file":
            uploaded = (files or {}).get(field_cfg.name)
            if uploaded:
                ui.label(f"{label}: uploaded").classes("text-positive text-sm")
            else:
                with ui.row().classes("items-center gap-2"):
                    ui.label(label).classes("text-sm")
                    if on_file_upload:
                        ui.upload(
                            label=t("file_upload"),
                            auto_upload=True,
                            on_upload=lambda e, name=field_cfg.name: on_file_upload(name, e),
                        ).props("dense flat").classes("max-w-xs")
            fields[field_cfg.name] = None  # files tracked separately
        elif field_cfg.type == "email":
            fields[field_cfg.name] = ui.input(
                label=label, value=value, validation={"Invalid email": lambda v: "@" in v if v else True}
            ).props("outlined dense type=email").classes("w-full")
        else:
            fields[field_cfg.name] = ui.input(
                label=label, value=value
            ).props("outlined dense").classes("w-full")

    # Completion status for partial-save steps
    if step.partial_save:
        _render_completion_indicator(step, data, files or {})

    with ui.row().classes("mt-4 gap-2"):
        if on_save_draft and step.partial_save:
            ui.button(t("save_draft"), on_click=lambda: on_save_draft(_collect_data(fields))).props(
                "flat"
            )

        async def validated_submit():
            collected = _collect_data(fields)
            missing = [
                f.label or f.name for f in step.fields
                if f.required and f.type != "file" and not collected.get(f.name)
            ]
            if missing:
                ui.notify(f"{t('required_field')}: {', '.join(missing)}", color="negative")
                return
            await on_submit(collected)

        ui.button(t("submit"), on_click=validated_submit).props("color=primary")

    return fields


def _render_completion_indicator(step: WorkflowStepConfig, data: dict, files: dict):
    """Show which required fields are filled for partial-save steps."""
    required = [f for f in step.fields if f.required]
    if not required:
        return
    filled = sum(
        1 for f in required
        if (f.type == "file" and files.get(f.name)) or (f.type != "file" and data.get(f.name))
    )
    ui.linear_progress(value=filled / len(required)).classes("w-full mb-2")
    ui.label(f"{filled}/{len(required)}").classes("text-sm text-grey")


def render_approval(
    request_data: dict,
    workflow,
    step: WorkflowStepConfig,
    on_approve,
    on_reject,
):
    """Render approval view: read-only data + approve/reject."""
    ui.label(workflow.label).classes("text-h6")

    for key, value in request_data.items():
        if value:
            ui.label(f"{key}: {value}").classes("text-sm")

    comment_input = ui.textarea(label=t("comment")).props("outlined dense").classes("w-full mt-2")

    with ui.row().classes("mt-4 gap-2"):
        ui.button(
            t("approve"),
            icon="check",
            on_click=lambda: on_approve(comment_input.value),
        ).props("color=positive")
        ui.button(
            t("reject"),
            icon="close",
            on_click=lambda: on_reject(comment_input.value),
        ).props("color=negative")


def render_status_badge(status: str):
    """Render a colored status badge."""
    colors = {
        "in_progress": "blue",
        "completed": "positive",
        "rejected": "negative",
    }
    color = colors.get(status, "grey")
    ui.badge(t(status), color=color)


def _collect_data(fields: dict) -> dict:
    """Collect values from UI fields."""
    return {
        name: (el.value if el is not None else None)
        for name, el in fields.items()
        if el is not None
    }


def _set_date(inp, menu, event):
    inp.value = event.value
    menu.close()


def _resolve_options(options_key: str | None) -> list[str]:
    """Resolve select field options from config."""
    if not options_key:
        return []
    from not_dot_net.config import get_settings
    settings = get_settings()
    if options_key == "teams":
        return settings.teams
    if options_key == "roles":
        from not_dot_net.backend.roles import Role
        return [r.value for r in Role]
    return []
