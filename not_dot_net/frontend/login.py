from typing import Optional

from fastapi.responses import RedirectResponse
from nicegui import app, ui

from not_dot_net.backend.users import authenticate_and_get_token


def setup():
    @ui.page("/login")
    def login(redirect_to: str = "/") -> Optional[RedirectResponse]:
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

        with ui.column().classes("absolute-center items-center gap-4"):
            ui.label("LPP Intranet").classes("text-h4 text-weight-light")
            with ui.card().classes("w-80"):
                email = ui.input("Email").props("outlined dense").classes(
                    "w-full"
                ).on("keydown.enter", try_login)
                password = ui.input(
                    "Password", password=True, password_toggle_button=True
                ).props("outlined dense").classes("w-full").on(
                    "keydown.enter", try_login
                )
                ui.button("Log in", on_click=try_login).classes("w-full")
        return None
