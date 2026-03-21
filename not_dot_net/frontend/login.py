from typing import Optional

from fastapi.responses import RedirectResponse
from nicegui import app, ui

from not_dot_net.backend.users import authenticate_and_get_token


def setup():
    @ui.page("/login")
    def login(redirect_to: str = "/user/profile") -> Optional[RedirectResponse]:
        if app.storage.user.get("authenticated", False):
            return RedirectResponse(redirect_to)

        async def try_login() -> None:
            try:
                token = await authenticate_and_get_token(email.value, password.value)
                if token is None:
                    ui.notify("Invalid email or password", color="negative")
                    return

                ui.run_javascript(
                    f'document.cookie = "fastapiusersauth={token}; path=/; SameSite=Lax";'
                    f'window.location.href = "{redirect_to}";'
                )
            except Exception:
                ui.notify("Auth server error", color="negative")

        with ui.card().classes("absolute-center"):
            email = ui.input("Email").on("keydown.enter", try_login)
            password = ui.input(
                "Password", password=True, password_toggle_button=True
            ).on("keydown.enter", try_login)
            ui.button("Log in", on_click=try_login)
        return None
