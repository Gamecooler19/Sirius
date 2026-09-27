"""Simple fixed-window rate limiting, backed by Valkey (Module 16 follow-up,
extended by Module 17 follow-up).

**Why this exists, and why only for `POST /auth/forgot-password` and
`POST /auth/change-email`.** Every other write endpoint in this codebase
requires either a valid credential (login: a real password guess) or an
already-authenticated session that only ever mutates the caller's *own*
account (`change_password`). These two endpoints share one specific
property none of the others do: each turns a caller-supplied string
into a real side effect -- an email landing in some inbox -- against a
**third party** who never had to prove they control that inbox.
`forgot-password` is unauthenticated, so this is obvious. `change-email`
is authenticated, but authentication only proves who the *caller* is,
not that `new_email` belongs to them -- a signed-in caller can still
name `victim@sirius.app` as the target and have this codebase send that
address mail, repeatedly, for free, exactly as an unauthenticated caller
can against `forgot-password`. Being authenticated changes who is
accountable for the request; it does not change where the harm lands.
See this module's own follow-up report, and Module 17's own follow-up
report, for the fuller decision writeups -- including why login and
`/auth/totp/verify` do *not* get one here (their entire cost lands on
the caller's own guess budget, not a third party).

**Design.** A plain fixed-window counter (`INCR` + `EXPIRE` on first
increment), not a sliding window or token bucket -- the simplest
correct mechanism for the threat this specifically defends against
(bulk mail-bombing one address), and consistent with this codebase's
general preference for the simplest mechanism that actually closes the
gap (e.g. `PasswordResetToken`'s own single fixed-TTL column, not a
more elaborate sliding-expiry scheme). Both limiters are keyed by the
**target email address** (lowercased) -- never by caller IP, and for
`change-email` specifically, never by the *caller's* account either --
the threat in both cases is "this inbox gets flooded," which a botnet
spread across many source IPs, or (for change-email) many different
authenticated accounts all naming the same victim address, would still
trigger against a single target; keying by anything other than the
target address itself would not close that specific gap.
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

# Same threshold/window as forgot-password -- see this module's own
# docstring for why `change-email` needs the identical protection
# (Module 17 follow-up).
CHANGE_EMAIL_RATE_LIMIT_MAX = 3
CHANGE_EMAIL_RATE_LIMIT_WINDOW_SECONDS = 15 * 60


async def _check_fixed_window_rate_limit(
    key: str, max_requests: int, window_seconds: int, error_message: str
) -> None:
    r = get_valkey()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_seconds)
    if count > max_requests:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, error_message)


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
    await _check_fixed_window_rate_limit(
        key=f"forgot_password_rl:{email.lower()}",
        max_requests=FORGOT_PASSWORD_RATE_LIMIT_MAX,
        window_seconds=FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
        error_message="too many password reset requests for this email; try again later",
    )


async def check_change_email_rate_limit(new_email: str) -> None:
    """Raises `429` once the **target `new_email`** has had more than
    `CHANGE_EMAIL_RATE_LIMIT_MAX` change-email requests aimed at it
    within the current window (Module 17 follow-up).

    **Keyed by the target address, deliberately not by the calling
    account.** The victim here is whoever owns `new_email`, not the
    caller -- a rate limit keyed by the *caller's* account would let a
    single attacker rotate through several different authenticated
    accounts (or simply keep using their own, since nothing here rate
    limits requests *from* an account, only requests *at* an address)
    to keep sending the same victim address confirmation mail past any
    per-account threshold. Keying by the target address closes that
    regardless of who -- or how many different accounts -- is doing the
    requesting, the same reasoning `check_forgot_password_rate_limit`
    already applies for its own, unauthenticated endpoint. Uses a
    distinct Valkey key prefix (`change_email_rl:`) from
    `forgot_password_rl:` so the two endpoints' windows never share or
    interfere with each other's counts, even if the same address is
    coincidentally targeted by both in the same window.
    """
    await _check_fixed_window_rate_limit(
        key=f"change_email_rl:{new_email.lower()}",
        max_requests=CHANGE_EMAIL_RATE_LIMIT_MAX,
        window_seconds=CHANGE_EMAIL_RATE_LIMIT_WINDOW_SECONDS,
        error_message="too many email-change requests for this address; try again later",
    )
