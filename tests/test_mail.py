import pytest
from unittest.mock import AsyncMock, patch
from not_dot_net.backend.mail import send_mail
from not_dot_net.config import MailSettings


async def test_dev_mode_logs_to_console(caplog):
    settings = MailSettings(dev_mode=True)
    with caplog.at_level("INFO", logger="not_dot_net.mail"):
        await send_mail(
            to="user@example.com",
            subject="Test Subject",
            body_html="<p>Hello</p>",
            mail_settings=settings,
        )
    assert "user@example.com" in caplog.text
    assert "Test Subject" in caplog.text


async def test_dev_catch_all_redirects(caplog):
    settings = MailSettings(dev_mode=True, dev_catch_all="catch@example.com")
    with caplog.at_level("INFO", logger="not_dot_net.mail"):
        await send_mail(
            to="real@example.com",
            subject="Test",
            body_html="<p>Hi</p>",
            mail_settings=settings,
        )
    assert "catch@example.com" in caplog.text
    assert "real@example.com" in caplog.text  # original still mentioned


async def test_production_mode_calls_aiosmtplib():
    settings = MailSettings(
        dev_mode=False,
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_tls=True,
        from_address="noreply@test.com",
    )
    with patch("not_dot_net.backend.mail.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await send_mail(
            to="user@example.com",
            subject="Prod Test",
            body_html="<p>Content</p>",
            mail_settings=settings,
        )
        mock_smtp.send.assert_called_once()
        msg = mock_smtp.send.call_args[0][0]
        assert msg["To"] == "user@example.com"
        assert msg["Subject"] == "Prod Test"
        assert msg["From"] == "noreply@test.com"


async def test_production_with_catch_all_redirects():
    settings = MailSettings(
        dev_mode=False,
        smtp_host="smtp.test.com",
        dev_catch_all="catch@example.com",
        from_address="noreply@test.com",
    )
    with patch("not_dot_net.backend.mail.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await send_mail(
            to="real@example.com",
            subject="Test",
            body_html="<p>Hi</p>",
            mail_settings=settings,
        )
        msg = mock_smtp.send.call_args[0][0]
        assert msg["To"] == "catch@example.com"
