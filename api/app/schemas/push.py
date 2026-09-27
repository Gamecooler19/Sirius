"""`uuid.UUID`/`str` request/response schemas for the push-subscription
endpoints (Module 20).
"""

from pydantic import BaseModel


class PushSubscribeRequest(BaseModel):
    """Mirrors the real shape `PushSubscription.toJSON()` produces in the
    browser (`endpoint`, `keys.p256dh`, `keys.auth`) -- the frontend
    sends this object's own JSON verbatim, not a reshaped version of it,
    so there is exactly one place (here) that decides the wire shape
    rather than two (the browser API's own shape and a second, invented
    one).
    """

    endpoint: str
    keys: "PushSubscriptionKeys"


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushUnsubscribeRequest(BaseModel):
    """`DELETE /notifications/subscribe` identifies which subscription
    row to remove by its own `endpoint` (the same value the browser's
    `PushSubscription.unsubscribe()` call reports) -- not by an id this
    frontend never otherwise handles, since the browser's own Push API
    hands back the endpoint, not a server-side row id.
    """

    endpoint: str


class VapidPublicKeyResponse(BaseModel):
    """`GET /notifications/vapid-public-key` -- the one public, non-
    secret value the frontend needs to call `pushManager.subscribe()`
    at all. Deliberately its own tiny endpoint rather than folding this
    into `MeResponse`: this value has nothing to do with the caller's
    own identity (it is the same for every account, including an
    unauthenticated visitor who has not opted in yet), so it does not
    belong on a response that is otherwise entirely about "who is this
    session."
    """

    public_key: str

