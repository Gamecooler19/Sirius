"""Real signed Web Push delivery (RFC 8030/8291/8292), Module 20.

**Why `pywebpush`, not a hand-rolled implementation.** `pywebpush` is
the standard Python library for this -- it owns RFC 8291's message
encryption (`aes128gcm`) and RFC 8292's VAPID JWT signing internally,
both cryptographic protocols this project has no reason to reimplement
or get subtly wrong. `app.core.crypto`'s own Fernet usage and
`app.core.totp`'s own `pyotp` usage are the same "use the standard
library for a cryptographic protocol, don't hand-roll it" precedent
this module follows.

**Why sync `pywebpush.webpush()` called via `asyncio.to_thread`, not an
async HTTP client.** The exact same precedent `app.core.mail.send_mail`
already established for `smtplib` (also sync, also wrapped in
`asyncio.to_thread` as "the cheap, defensive choice, not a load-bearing
one" per that module's own docstring) -- `pywebpush` is built on the
synchronous `requests` library internally with no async variant, and
introducing a second HTTP client dependency solely to avoid one
`to_thread` call for a feature already running inside a `BackgroundTasks`
callback (see `app.routers.applicant_create`/`app.routers.payment_claim`
for where this is actually called from -- never on the request's own
critical path) would be complexity this project's existing precedent
does not ask for.

**Dead-subscription cleanup (the module's own explicit requirement).**
A push service returns `404`/`410` when a subscription's endpoint is
permanently gone -- the browser unsubscribed, the user cleared site
data, the subscription itself expired. `send_push_to_user` deletes that
`PushSubscription` row the moment either code is seen, rather than
leaving it to fail identically, silently, on every future event
targeting that user. Any other non-2xx response (a transient 5xx from
the push service, a malformed request on this server's own side) is
logged but the row is left alone -- only `404`/`410` are the *standard*
"this subscription is permanently dead" signal (RFC 8030 SS7, and every
real push-service implementation's documented behavior); a transient
failure deleting a still-valid subscription would be a worse outcome
than leaving a truly dead one around for one more failed attempt.
"""

import asyncio
import json
import logging
import uuid

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.models.push_subscription import PushSubscription
from app.models.role import Role
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

# Codes a push service uses to mean "this subscription's endpoint is
# permanently gone" -- RFC 8030 SS7's own documented behavior, and the
# module's own explicit requirement for when to delete the row.
_DEAD_SUBSCRIPTION_STATUS_CODES = frozenset({404, 410})


def _send_sync(subscription: PushSubscription, payload_json: str) -> int | None:
    """Sends one real push, returns the push service's own HTTP status
    code (so the async caller can decide whether to delete the row),
    or `None` if the send raised for a reason that carries no status
    code at all (a network-level failure, not a push-service response).
    """
    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload_json,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
        )
        # webpush() only returns (rather than raising) on a 2xx/202 --
        # see its own source: any status > 202 raises WebPushException
        # with the real requests.Response attached, which is exactly
        # what the except branch below reads back out.
        return response.status_code
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        logger.warning(
            "push delivery failed for subscription %s: %s (status=%s)",
            subscription.id,
            exc.message,
            status_code,
        )
        return status_code


async def send_push_to_user(
    db: AsyncSession, user_id: uuid.UUID, title: str, body: str, url: str
) -> None:
    """Sends a real push to every subscription this user currently has
    registered (ordinarily one, but nothing here assumes exactly one --
    a user with two browsers subscribed gets the notification on both,
    the correct behavior for a real multi-device account). `url` is the
    in-app route the frontend's own `notificationclick` handler
    navigates to -- see `frontend/public/sw.js`'s own comment for the
    two concrete routes this module wires (an applicant's detail page,
    the finance queue).

    Deliberately takes an already-open `db` session rather than opening
    its own -- callers run this from inside a `BackgroundTasks` callback
    *after* the triggering request's own transaction has already
    committed (see the call sites' own comments for why), at which point
    a fresh, unscoped `get_db()`-style session is exactly what is needed
    to read `PushSubscription` rows for a user who is not the calling
    request's own actor -- see `app.models.push_subscription`'s own
    docstring for why this table is unscoped by RLS in the first place.
    """
    subscriptions = (
        await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
    ).scalars().all()

    if not subscriptions:
        return

    payload_json = json.dumps({"title": title, "body": body, "url": url})

    for subscription in subscriptions:
        status_code = await asyncio.to_thread(_send_sync, subscription, payload_json)
        if status_code in _DEAD_SUBSCRIPTION_STATUS_CODES:
            logger.info(
                "deleting dead push subscription %s (user %s, status %s)",
                subscription.id,
                user_id,
                status_code,
            )
            await db.execute(
                delete(PushSubscription).where(PushSubscription.id == subscription.id)
            )
            await db.commit()


async def send_push_to_users(
    db: AsyncSession, user_ids: list[uuid.UUID], title: str, body: str, url: str
) -> None:
    """Fan-out helper for the multi-recipient case (e.g. "every
    `SUPER_ADMIN`/`ADMISSIONS_MANAGER`" for an unassigned applicant, or
    "every `FINANCE_MANAGER`/`SUPER_ADMIN`" for a pending claim) -- a
    thin loop over `send_push_to_user`, not a separate fan-out
    implementation, so the dead-subscription cleanup and payload shape
    stay in exactly one place.
    """
    for user_id in user_ids:
        await send_push_to_user(db, user_id, title, body, url)


async def get_active_user_ids_for_roles(db: AsyncSession, role_codes: list[str]) -> list[uuid.UUID]:
    """Every active account whose role is in `role_codes` -- the exact
    recipient-resolution step both real triggers in this module use
    (`app.routers.applicant_create`'s unassigned-applicant case,
    `app.routers.payment_claim`'s new-claim case), so "which roles
    should this event notify" and "which live user ids does that role
    set currently resolve to" stay two clearly separate, individually
    readable steps rather than one inlined query duplicated at each call
    site. `is_active` filtered here (not left to the push-send step to
    discover): a deactivated account's own session can no longer
    authenticate at all, so it has no way to ever see or act on a
    notification even if push delivery to it somehow still worked.
    """
    rows = (
        await db.execute(
            select(User.id)
            .join(Role, User.role_id == Role.id)
            .where(Role.code.in_(role_codes), User.is_active.is_(True))
        )
    ).scalars().all()
    return list(rows)


async def notify_in_background(user_ids: list[uuid.UUID], title: str, body: str, url: str) -> None:
    """The one entry point every `BackgroundTasks.add_task(...)` call
    site in this module actually schedules (see
    `app.routers.applicant_create.create_applicant` and
    `app.routers.payment_claim.submit_payment_claim` for the two real
    call sites) -- opens its own fresh, unscoped session via
    `async_session_factory` rather than reusing the triggering request's
    own session, because a `BackgroundTasks` callback runs *after* the
    response has already been sent and that request's own
    `open_scoped_session` transaction has already closed (FastAPI's own
    documented behavior, not an assumption); reusing a closed session
    object here would raise the same `InvalidRequestError`
    `app.core.db.open_scoped_session`'s own docstring already documents
    for a different closed-session-reuse case. A fresh, unscoped session
    is also the structurally correct choice regardless, independent of
    the closed-transaction issue: `PushSubscription` is deliberately
    RLS-unscoped (see that model's own docstring), so there is no
    `app.actor_role`/`app.actor_id` GUC this background delivery step
    needs or should set -- it is not acting *as* any particular user,
    it is the system delivering an already-decided notification to an
    already-decided recipient list.
    """
    async with async_session_factory() as db, db.begin():
        await send_push_to_users(db, user_ids, title, body, url)
