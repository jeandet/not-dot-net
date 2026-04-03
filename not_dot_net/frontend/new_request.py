"""New Request tab — pick a workflow type and fill the first step."""

from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.permissions import has_permissions
from not_dot_net.backend.workflow_service import create_request, workflows_config
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import render_step_form


async def render(user: User):
    """Render the new request tab content."""
    cfg = await workflows_config.get()
    container = ui.column().classes("w-full")

    with container:
        ui.label(t("select_workflow")).classes("text-h6 mb-4")

        for wf_key, wf_config in cfg.workflows.items():
            if not await has_permissions(user, "create_workflows"):
                continue

            with ui.card().classes("w-full cursor-pointer") as card:
                ui.label(wf_config.label).classes("font-bold")

                form_container = ui.column().classes("w-full mt-2")
                form_container.set_visibility(False)
                form_container.on("click.stop", js_handler="() => {}")

                first_step = wf_config.steps[0]

                async def handle_submit(data, key=wf_key, fc=form_container):
                    await create_request(
                        workflow_type=key,
                        created_by=user.id,
                        data=data,
                        actor=user,
                    )
                    ui.notify(t("request_created"), color="positive")
                    fc.set_visibility(False)

                async def toggle_form(fc=form_container, step=first_step):
                    visible = not fc.visible
                    fc.set_visibility(visible)
                    if visible:
                        fc.clear()
                        with fc:
                            await render_step_form(step, {}, on_submit=handle_submit)

                card.on("click", toggle_form)
