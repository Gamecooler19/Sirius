"""Real SMTP mail sending (Module 16), through the local Mailpit dev server
(`deploy/docker-compose.yml`'s own `mailpit` service) -- no third-party
email API, no external provider, no API key.

**Why stdlib `smtplib`, not an async SMTP library.** This codebase already
has one precedent for a sync, blocking library called from an async route
handler: `app.services.excel_import.parse_workbook` wraps `openpyxl`
(also sync) and is called directly from `import_.import_applicants`
without `asyncio.to_thread`. `smtplib.SMTP.sendmail` against a local
Mailpit container on the same Docker bridge network is a few-millisecond
operation (no real network latency, no external DNS, no TLS handshake --
Mailpit accepts plain unauthenticated SMTP), not a meaningfully
blocking call worth the extra complexity of an async SMTP client
dependency for a project this size. `asyncio.to_thread` is used anyway
below, not because the operation is slow, but because it costs nothing
and keeps the event loop technically non-blocking even under a future
slower SMTP target -- the cheap, defensive choice, not a load-bearing one.

**No real delivery ever leaves this stack.** Mailpit is a dev-only SMTP
sink: every email sent through it is captured, never actually delivered
to a real mailbox. This module has no code path that could reach a real
SMTP relay -- `SMTP_HOST`/`SMTP_PORT` are hardcoded to `mailpit`/`1025`
in `deploy/docker-compose.yml`, not attacker- or user-controlled.
"""

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


def _send_sync(to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = to_address
    message.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as client:
        client.send_message(message)


async def send_mail(to_address: str, subject: str, body: str) -> None:
    """Sends a real email via SMTP to Mailpit. Runs the blocking
    `smtplib` call in a thread (see this module's own docstring for why
    that is a defensive, not load-bearing, choice here).
    """
    await asyncio.to_thread(_send_sync, to_address, subject, body)
