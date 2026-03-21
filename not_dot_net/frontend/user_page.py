from typing import Optional

from fastapi import Depends
from fastapi.responses import RedirectResponse
from nicegui import ui

from not_dot_net.backend.db import User
from not_dot_net.backend.users import current_active_user_optional


def setup():
    @ui.page("/user/profile")
    def user_page(
        user: Optional[User] = Depends(current_active_user_optional),
    ) -> Optional[RedirectResponse]:
        if not user:
            ui.notify("Please log in to access your user profile", color="warning")
            return RedirectResponse("/login")
        with ui.card().classes("absolute-center"):
            ui.label(f"User Page for User ID: {user.id}")
            ui.label(f"Email: {user.email}")
            ui.button("Go to Main Page", on_click=lambda: ui.navigate.to("/"))
        return None
