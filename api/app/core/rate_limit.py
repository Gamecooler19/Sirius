"""Simple fixed-window rate limiting, backed by Valkey (Module 16 follow-up).

**Why this exists, and why only for `POST /auth/forgot-password`.** Every
other write endpoint in this codebase requires either a valid credential
(login: a real password guess) or an already-authenticated session
(everything behind `get_current_user`). `POST /auth/forgot-password` is
the one endpoint that turns an arbitrary caller-supplied string into a
real side effect against a *third party* -- an email landing in some
inbox -- without the caller ever having to prove they control that
inbox. A caller who does not own `victim@sirius.app` can still make
this endpoint send that address mail, repeatedly, for free. That is a
materially different risk from a login brute-force attempt (which only
ever affects the attacker's own guess accuracy, not a third party's
inbox), and is the actual reason this endpoint -- and only this one --
gets a rate limit in this codebase. See this module's own follow-up
report for the fuller decision writeup, including why login and
`/auth/totp/verify` do *not* get one here.

**Design.** A plain fixed-window counter (`INCR` + `EXPIRE` on first
increment), not a sliding window or token bucket -- the simplest
correct mechanism for the threat this specifically defends against
(bulk mail-bombing one address), and consistent with this codebase's
general preference for the simplest mechanism that actually closes the
gap (e.g. `PasswordResetToken`'s own single fixed-TTL column, not a
more elaborate sliding-expiry scheme). Keyed by the **target email
address** (lowercased), not by caller IP -- the threat is "this inbox
gets flooded," which a botnet spread across many source IPs would still
trigger against a single victim address; IP-keying would not close that
specific gap.
"""

from fastapi import HTTPException, status

from app.core.valkey import get_valkey

# 3 requests per 15-minute window per target email. Generous enough that
# a real user who mistypes their password twice and requests a reset
# each time is never throttled, tight enough that a script sending this
# endpoint hundreds of requests against one victim address in a burst
# is stopped after the third.
FORGOT_PASSWORD_RATE_LIMIT_MAX = 3
FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS = 15 * 60


async def check_forgot_password_rate_limit(email: str) -> None:
    """Raises `429` once the target email has been requested more than
    `FORGOT_PASSWORD_RATE_LIMIT_MAX` times within the current window.

    **Does not itself leak account existence.** The counter is keyed by
    the raw requested email string, before any database lookup -- a
    caller spamming a nonexistent address gets throttled at exactly the
    same threshold as one spamming a real account, so a `429` here
    carries no information about whether the account exists (unlike a
    response that only appeared for one of the two cases, which would
    reopen the exact enumeration gap `ForgotPasswordResponse`'s own
    generic-message guarantee already closes).
    """
    r = get_valkey()
    key = f"forgot_password_rl:{email.lower()}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS)
    if count > FORGOT_PASSWORD_RATE_LIMIT_MAX:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many password reset requests for this email; try again later",
        )
