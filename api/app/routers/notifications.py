"""Push-subscription registration (Module 20): lets an authenticated
account register or remove *this browser's* Web Push subscription, plus
a public VAPID-key lookup unauthenticated code (the service worker's own
subscribe call) needs before a session even exists in the ordinary
sense.

**RBAC: any authenticated session, all six roles.** Notification
*delivery* is what reuses this project's existing RBAC/RLS boundaries
(see `app.core.push`'s own docstring, and the two real trigger sites in
`app.routers.applicant_create`/`app.routers.payment_claim`) -- but
*registering a subscription at all* is not itself a privileged action
for any particular role; every account, regardless of role, is
something a future event might need to notify (a counselor's own
walk-in creation, a finance manager's own pending claim), so gating
subscription registration itself to a role subset would be gating the
wrong thing.

**Identity sourced exclusively from the session**, the same "trust the
session, never the body" rule every other self-service mutation in this
codebase already establishes (`ChangeNameRequest`/
`ChangePasswordRequest`'s own docstrings) -- neither request schema
carries a `user_id` field.

**Upsert on `POST`, not reject-on-collision.** A subscribe call for an
`endpoint` this table already has (the same browser re-subscribing,
e.g. after clearing local state, or simply calling `subscribe()` again)
updates the existing row's `p256dh`/`auth` in place rather than
rejecting with a uniqueness conflict -- a push service's own subscribe
flow has no concept of "you already did this," and neither should this
endpoint.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_scoped_session, get_current_user
from app.core.sessions import SessionData
from app.models.push_subscription import PushSubscription
from app.schemas.push import PushSubscribeRequest, PushUnsubscribeRequest, VapidPublicKeyResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])
settings = get_settings()


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key() -> VapidPublicKeyResponse:
    """Deliberately unauthenticated -- a VAPID public key is not a
    secret (the whole point of VAPID's asymmetric-key design is that
    the public half can be handed to any browser freely; only the
    *private* key, held exclusively by this server via
    `settings.VAPID_PRIVATE_KEY`, ever signs anything) -- and the
    frontend's own opt-in control (`ProfilePage`) needs this value
    before the user has necessarily done anything else that would
    establish a fuller authenticated context, so requiring a session
    here would be an arbitrary restriction on a genuinely public value.
    """
    return VapidPublicKeyResponse(public_key=settings.VAPID_PUBLIC_KEY)


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(
    body: PushSubscribeRequest,
    session: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_scoped_session),
) -> None:
    user_id = uuid.UUID(session.user_id)

    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Upsert -- see module docstring. Also re-points user_id at the
        # current caller: a shared/kiosk browser where a different
        # account subscribes on the same endpoint should transfer
        # ownership of the subscription to whoever most recently opted
        # in on it, not silently keep notifying the previous account.
        existing.user_id = user_id
        existing.p256dh = body.keys.p256dh
        existing.auth = body.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=user_id,
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
            )
        )

    await db.flush()


@router.delete("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    body: PushUnsubscribeRequest,
    session: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_scoped_session),
) -> None:
    """Removes *this browser's* subscription row, identified by its own
    `endpoint` -- scoped to the caller's own `user_id` too (not merely
    "delete whatever row has this endpoint"), so one account cannot
    unsubscribe a different account's registration even if it somehow
    learned that endpoint string. A call for an endpoint this account
    never registered (or already removed) is a silent no-op, not a 404
    -- unsubscribing something that is already gone is not an error
    from the caller's own point of view, the same "idempotent delete"
    convention `logout`/`destroy_session` already follow elsewhere in
    this codebase.
    """
    user_id = uuid.UUID(session.user_id)
    await db.execute(
        PushSubscription.__table__.delete().where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user_id
        )
    )
