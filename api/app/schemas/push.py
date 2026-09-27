"""`uuid.UUID`/`str` request/response schemas for the push-subscription
endpoints (Module 20).
"""

import base64
import binascii

from pydantic import BaseModel, field_validator


def _validate_base64url(value: str, field_name: str) -> str:
    """Rejects a `p256dh`/`auth` value that is not real base64url --
    the exact defect class found live during this module's own
    verification: a malformed key stored via this endpoint would not
    fail until the much later, much more damaging point of an actual
    push *send* (`pywebpush`'s own `binascii.Error`, raised deep inside
    its encryption setup, see `app.core.push._send_sync`'s own
    docstring for the full account), by which point it can abort
    delivery to every other recipient in the same notification batch
    if the caller's own exception handling is not airtight everywhere
    -- defense in depth, not a substitute for that fix, but a real key
    should never reach the database in the first place. Padding is
    added defensively before decoding (the browser's own
    `PushSubscription.toJSON()` output is unpadded base64url, RFC 7515
    JWS-style, the standard the Web Push spec itself follows), so a
    genuine, correctly-unpadded real key is never rejected by this
    check -- only a value that cannot be base64url under any padding
    is.
    """
    padded = value + "=" * (-len(value) % 4)
    try:
        base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{field_name} must be valid base64url") from exc
    return value


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

    @field_validator("p256dh")
    @classmethod
    def _validate_p256dh(cls, value: str) -> str:
        return _validate_base64url(value, "p256dh")

    @field_validator("auth")
    @classmethod
    def _validate_auth(cls, value: str) -> str:
        return _validate_base64url(value, "auth")


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

