"""The one place the session cookie's attributes are set.

httpOnly: JavaScript cannot read this cookie (`document.cookie` never sees
it), closing the most common XSS-to-session-theft path.
SameSite=Strict: the browser never attaches this cookie to a cross-site
request, including top-level navigation from another origin -- the
strongest of the three SameSite modes, appropriate here because this is an
internal admissions/finance tool with no legitimate cross-site linking flow
that would need Lax's relaxation.
Secure: gated on `settings.SESSION_COOKIE_SECURE` (see that setting's own
docstring) rather than hardcoded True, because local development runs over
plain HTTP and a Secure cookie is invisible to a plain-HTTP browser --
every real deployment must set this true.
"""

from fastapi import Response

from app.core.config import get_settings
from app.core.sessions import SESSION_TTL_SECONDS

settings = get_settings()

SESSION_COOKIE_NAME = "univadmissions_session"


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
