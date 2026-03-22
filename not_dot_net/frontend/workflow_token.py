"""Standalone token page — no login required."""

from nicegui import ui

from not_dot_net.backend.workflow_service import (
    get_request_by_token,
    save_draft,
    submit_step,
)
from not_dot_net.backend.workflow_engine import get_current_step_config
from not_dot_net.config import get_settings
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import render_step_form


def setup():
    @ui.page("/workflow/token/{token}")
    async def token_page(token: str):
        req = await get_request_by_token(token)

        if req is None:
            with ui.column().classes("absolute-center items-center"):
                ui.icon("error", size="xl", color="negative")
                ui.label(t("token_expired")).classes("text-h6")
            return

        settings = get_settings()
        wf = settings.workflows.get(req.type)
        if not wf:
            ui.label(t("token_expired"))
            return

        step_config = get_current_step_config(req, wf)
        if not step_config:
            ui.label(t("token_expired"))
            return

        with ui.column().classes("max-w-2xl mx-auto p-6"):
            ui.label(wf.label).classes("text-h5 mb-2")
            ui.label(t("token_welcome")).classes("text-grey mb-4")

            form_container = ui.column().classes("w-full")

            async def handle_submit(data):
                await submit_step(
                    req.id, actor_id=None, action="submit", data=data,
                )
                form_container.clear()
                with form_container:
                    ui.icon("check_circle", size="xl", color="positive")
                    ui.label(t("step_submitted")).classes("text-h6")

            async def handle_save_draft(data):
                await save_draft(
                    req.id, data=data, actor_token=token,
                )
                ui.notify(t("draft_saved"), color="positive")

            with form_container:
                render_step_form(
                    step_config,
                    req.data,
                    on_submit=handle_submit,
                    on_save_draft=handle_save_draft if step_config.partial_save else None,
                )
