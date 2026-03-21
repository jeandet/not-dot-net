from nicegui.testing import User


async def test_login_page_renders(user: User) -> None:
    await user.open("/login")
    await user.should_see("Log in")
