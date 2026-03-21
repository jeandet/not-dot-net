from nicegui.testing import User


async def test_login_page_renders(user: User) -> None:
    await user.open("/login")
    await user.should_see("Log in")


async def test_main_page_redirects_when_unauthenticated(user: User) -> None:
    await user.open("/")
    await user.should_see("Log in")


async def test_login_page_shows_app_title(user: User) -> None:
    await user.open("/login")
    await user.should_see("LPP Intranet")
