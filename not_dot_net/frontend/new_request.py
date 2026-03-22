"""New Request tab — pick a workflow type and fill the first step."""

from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.roles import Role, has_role
from not_dot_net.backend.workflow_service import create_request
from not_dot_net.config import get_settings
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import render_step_form


def render(user: User):
    """Render the new request tab content."""
    settings = get_settings()
    container = ui.column().classes("w-full")

    with container:
        ui.label(t("select_workflow")).classes("text-h6 mb-4")

        for wf_key, wf_config in settings.workflows.items():
            if not has_role(user, Role(wf_config.start_role)):
                continue

            with ui.card().classes("w-full cursor-pointer") as card:
                ui.label(wf_config.label).classes("font-bold")

                form_container = ui.column().classes("w-full mt-2")
                form_container.set_visibility(False)

                first_step = wf_config.steps[0]

                async def handle_submit(data, key=wf_key, fc=form_container):
                    await create_request(
                        workflow_type=key,
                        created_by=user.id,
                        data=data,
                    )
                    ui.notify(t("request_created"), color="positive")
                    fc.set_visibility(False)

                def toggle_form(fc=form_container, step=first_step):
                    visible = not fc.visible
                    fc.set_visibility(visible)
                    if visible:
                        fc.clear()
                        with fc:
                            render_step_form(step, {}, on_submit=handle_submit)

                card.on("click", toggle_form)
