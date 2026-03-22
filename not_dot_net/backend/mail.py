"""Async mail sending with dev-mode logging."""

import logging
from email.message import EmailMessage

import aiosmtplib

from not_dot_net.config import MailSettings

logger = logging.getLogger("not_dot_net.mail")


async def send_mail(
    to: str,
    subject: str,
    body_html: str,
    mail_settings: MailSettings,
) -> None:
    effective_to = to
    if mail_settings.dev_catch_all:
        effective_to = mail_settings.dev_catch_all

    if mail_settings.dev_mode:
        logger.info("[MAIL dev] To: %s (original: %s) Subject: %s", effective_to, to, subject)
        return

    msg = EmailMessage()
    msg["From"] = mail_settings.from_address
    msg["To"] = effective_to
    msg["Subject"] = subject
    msg.set_content(body_html, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=mail_settings.smtp_host,
        port=mail_settings.smtp_port,
        start_tls=mail_settings.smtp_tls,
        username=mail_settings.smtp_user or None,
        password=mail_settings.smtp_password or None,
    )
