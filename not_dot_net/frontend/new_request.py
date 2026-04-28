"""New Request tab — pick a workflow type and fill the first step."""

from nicegui import app, ui
from sqlalchemy import select, or_

from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.permissions import has_permissions
from not_dot_net.backend.workflow_service import create_request, submit_step, workflows_config
from not_dot_net.frontend.i18n import t
from not_dot_net.frontend.workflow_step import render_step_form

_CLONE_DATE_FIELDS = {"departure_date", "return_date", "start_date", "end_date"}


async def _search_users(query: str) -> list[dict]:
    """Search all users (including inactive) by name or email."""
    if not query or len(query) < 2:
        return []
    async with session_scope() as session:
        pattern = f"%{query}%"
        result = await session.execute(
            select(User).where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                )
            ).limit(10)
        )
        return [
            {"id": str(u.id), "email": u.email, "name": u.full_name or u.email, "active": u.is_active}
            for u in result.scalars().all()
        ]


async def render(user: User):
    """Render the new request tab content."""
    cfg = await workflows_config.get()
    clone = app.storage.user.pop("clone_prefill", None)
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
                    req = await create_request(
                        workflow_type=key,
                        created_by=user.id,
                        data=data,
                        actor=user,
                    )
                    await submit_step(
                        request_id=req.id,
                        actor_id=user.id,
                        action="submit",
                        data=data,
                        actor_user=user,
                    )
                    ui.notify(t("request_created"), color="positive")
                    fc.set_visibility(False)

                async def _open_form(fc=form_container, step=first_step, key=wf_key, prefill_data=None, submit_fn=handle_submit):
                    fc.clear()
                    fc.set_visibility(True)
                    with fc:
                        prefill = dict(prefill_data or {})
                        if key == "onboarding":
                            prefill.update(await _render_returning_search(fc))
                        await render_step_form(step, prefill, on_submit=submit_fn)

                async def toggle_form(fc=form_container, step=first_step, key=wf_key, open_fn=_open_form):
                    if fc.visible:
                        fc.set_visibility(False)
                    else:
                        await open_fn(fc, step, key)

                card.on("click", toggle_form)

                if clone and clone.get("type") == wf_key:
                    clone_data = {k: v for k, v in clone.get("data", {}).items() if k not in _CLONE_DATE_FIELDS}
                    ui.timer(0, lambda fc=form_container, step=first_step, key=wf_key, cd=clone_data:
                             _open_form(fc, step, key, cd), once=True)


async def _render_returning_search(container) -> dict:
    """Render returning-person search. Returns prefill data dict."""
    prefill = {}
    results_container = ui.column().classes("w-full")

    async def on_search(e):
        matches = await _search_users(search_input.value)
        results_container.clear()
        with results_container:
            for match in matches:
                active_label = "" if match["active"] else " (inactive)"
                async def select_user(m=match):
                    nonlocal prefill
                    prefill["contact_email"] = m["email"]
                    prefill["returning_user_id"] = m["id"]
                    search_input.value = m["name"]
                    results_container.clear()
                    with results_container:
                        ui.chip(
                            f"Returning: {m['name']}{active_label}",
                            icon="person",
                            color="blue",
                        )
                ui.item(f"{match['name']} — {match['email']}{active_label}", on_click=select_user)

    with ui.expansion(t("search_existing"), icon="search").classes("w-full mb-2"):
        search_input = ui.input(label=t("search_by_name_email")).props("outlined dense")
        search_input.on("keyup", on_search, throttle=0.3)
        results_container

    return prefill
