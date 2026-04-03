"""First-run setup wizard — shown when no admin user exists (production only)."""

from nicegui import ui
from sqlalchemy import select

from not_dot_net.backend.db import User, session_scope
from not_dot_net.backend.roles import Role
from not_dot_net.backend.users import ensure_default_admin
from not_dot_net.config import org_config, OrgConfig


async def has_admin() -> bool:
    async with session_scope() as session:
        result = await session.execute(
            select(User).where(User.role == Role.ADMIN).limit(1)
        )
        return result.scalar_one_or_none() is not None


def setup():
    @ui.page("/setup")
    async def setup_page():
        if await has_admin():
            ui.navigate.to("/login")
            return

        email = ui.input("Admin Email").props("outlined")
        password = ui.input("Admin Password", password=True, password_toggle_button=True).props("outlined")
        app_name = ui.input("Application Name", value="LPP Intranet").props("outlined")

        async def on_submit():
            if not email.value or not password.value:
                ui.notify("Email and password required", color="negative")
                return
            await ensure_default_admin(email.value, password.value)
            if app_name.value:
                cfg = await org_config.get()
                await org_config.set(cfg.model_copy(update={"app_name": app_name.value}))
            ui.navigate.to("/login")

        ui.button("Complete Setup", on_click=on_submit).props("color=primary")
