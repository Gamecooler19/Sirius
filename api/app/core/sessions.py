"""Server-side session store, backed by Valkey.

**Design.** A session id is an opaque random string (`secrets.token_urlsafe`,
256 bits of entropy), never a JWT -- the client only ever needs to present it
back; the server looks up its meaning. The httpOnly/Secure/SameSite=Strict
cookie (`app.core.cookies`) carries this id and nothing else; every fact
about the session (user id, role, whether TOTP has been verified this
session) lives server-side in Valkey, keyed by the id, so a stolen cookie
without the corresponding Valkey entry is worthless, and revoking a session
(logout, or an administrator force-logout) is one Valkey delete rather than
waiting out a token's own expiry.

**Payload encryption.** The JSON payload is Fernet-encrypted
(`app.core.crypto.encrypt_session_payload`) before it is written to Valkey.
Valkey itself has no RLS or access control of its own the way Postgres
does -- encrypting the payload at the application layer means a Valkey-level
compromise (a misconfigured network exposure, an operator with Valkey
access but no reason to see user ids/roles) does not, by itself, hand over
every live session's identity, only opaque ciphertext.

**TOTP-pending sessions.** A session created by a successful password check
but not yet TOTP-verified (`totp_verified: False`) is a real, distinct
Valkey entry from a fully-authenticated one, not a separate mechanism --
`app.core.deps.get_current_user` will require `totp_verified: True` on every
route after `require_totp_if_mandatory` gates on `role` deciding TOTP is
mandatory for that user. This means a TOTP-pending session cannot be used to
reach any protected route by simply omitting the second factor -- there is
no protected route that does not check `totp_verified` once the role
requires it.

**Per-user session index, for administrator force-logout
(Module 15 follow-up).** A secondary Valkey set,
`user_sessions:{user_id}`, tracks every session id currently open for that
user -- maintained by `create_session` (adds on login) and `destroy_session`
(removes on logout). `destroy_sessions_for_user` reads that set and deletes
every session key it names, then deletes the set itself; this is what
`POST /users/{id}/reset-totp` calls so a stolen-device TOTP reset actually
logs the account out immediately, not merely on its *next* login (see that
route's own docstring for the full reasoning). Stale members (a session
that already expired via its own TTL, or a `destroy_session` call that
predates this index existing) are harmless: deleting an already-gone
`session:*` key is a no-op, not an error.
"""

import json
import secrets
import uuid
from dataclasses import asdict, dataclass

from app.core.crypto import decrypt_session_payload, encrypt_session_payload
from app.core.valkey import get_valkey

SESSION_TTL_SECONDS = 12 * 60 * 60  # 12 hours idle timeout


@dataclass
class SessionData:
    user_id: str
    role_code: str
    totp_verified: bool


def _session_key(session_id: str) -> str:
    return f"session:{session_id}"


def _user_sessions_key(user_id: str) -> str:
    return f"user_sessions:{user_id}"


async def create_session(user_id: uuid.UUID, role_code: str, totp_verified: bool) -> str:
    session_id = secrets.token_urlsafe(32)
    data = SessionData(user_id=str(user_id), role_code=role_code, totp_verified=totp_verified)
    payload = encrypt_session_payload(json.dumps(asdict(data)))
    r = get_valkey()
    await r.set(_session_key(session_id), payload, ex=SESSION_TTL_SECONDS)
    # Index this session under its owning user so an administrator action
    # (reset-TOTP, a future force-logout) can find and destroy every
    # session this user currently has open, without a full Valkey scan.
    user_key = _user_sessions_key(str(user_id))
    await r.sadd(user_key, session_id)
    await r.expire(user_key, SESSION_TTL_SECONDS)
    return session_id


async def read_session(session_id: str) -> SessionData | None:
    r = get_valkey()
    payload = await r.get(_session_key(session_id))
    if payload is None:
        return None
    raw = json.loads(decrypt_session_payload(payload))
    return SessionData(**raw)


async def mark_totp_verified(session_id: str) -> None:
    data = await read_session(session_id)
    if data is None:
        return
    data.totp_verified = True
    payload = encrypt_session_payload(json.dumps(asdict(data)))
    r = get_valkey()
    await r.set(_session_key(session_id), payload, ex=SESSION_TTL_SECONDS, keepttl=False)


async def mark_totp_pending(session_id: str) -> None:
    """The mirror-image write of `mark_totp_verified` (Module 18,
    `POST /auth/totp/self-reset`): flips an already-verified session's
    `totp_verified` back to `False` in place, without deleting the
    session itself. This is what actually forces the *same* session
    that just disabled its own old TOTP secret through a real,
    fresh `enroll/start` + `enroll/confirm` cycle before it can reach
    any route depending on `get_current_user` again -- the session
    stays alive (`get_current_session` still resolves it, which is all
    `enroll/start`/`enroll/confirm` themselves require), but is back in
    the same TOTP-pending state a brand new mandatory-TOTP login
    produces, closing the window where a self-reset account could
    otherwise keep using protected routes on the strength of a second
    factor it just voluntarily discarded.
    """
    data = await read_session(session_id)
    if data is None:
        return
    data.totp_verified = False
    payload = encrypt_session_payload(json.dumps(asdict(data)))
    r = get_valkey()
    await r.set(_session_key(session_id), payload, ex=SESSION_TTL_SECONDS, keepttl=False)


async def destroy_session(session_id: str) -> None:
    r = get_valkey()
    data = await read_session(session_id)
    if data is not None:
        await r.srem(_user_sessions_key(data.user_id), session_id)
    await r.delete(_session_key(session_id))


async def destroy_sessions_for_user(user_id: uuid.UUID) -> int:
    """Force-logout: deletes every Valkey session currently open for this
    user, via the `user_sessions:{user_id}` index `create_session`
    maintains. Returns the number of session keys actually deleted (0 if
    the user had no live session at all, which is the common case for a
    reset-TOTP call against an account that is not currently logged in).
    """
    r = get_valkey()
    user_key = _user_sessions_key(str(user_id))
    session_ids = await r.smembers(user_key)
    deleted = 0
    for session_id in session_ids:
        deleted += await r.delete(_session_key(session_id))
    await r.delete(user_key)
    return deleted


async def destroy_other_sessions_for_user(user_id: uuid.UUID, keep_session_id: str) -> int:
    """Force-logout every session for this user **except** one
    (Module 18, `POST /auth/totp/self-reset`) -- a genuine, deliberate
    variant of `destroy_sessions_for_user`'s blanket behavior, not the
    same call reused unchanged.

    **Why this needs to exist separately.** Self-service TOTP
    re-enrollment is, by construction, performed *from within* an
    already-live, fully-authenticated session -- the caller is sitting
    in the middle of the very request that is about to invalidate every
    session for their own account. `destroy_sessions_for_user`'s
    blanket "delete every session this user has open" would delete the
    acting session too, breaking the multi-step flow it is itself
    running (self-reset succeeds, then the client immediately calls
    `/auth/totp/enroll/start` + `/confirm` against what it still
    believes is a live session -- a session that blanket deletion would
    have just destroyed out from under it). The threat model this
    force-logout defends against is a *different* device or browser
    that authenticated earlier and is still sitting on the old,
    now-replaced second factor; the session actively performing the
    reset is not that threat, it is the legitimate action itself.

    Reads the same `user_sessions:{user_id}` index `create_session`
    maintains, deletes every member except `keep_session_id`, and
    removes only the deleted ids from the index set (not the whole set,
    unlike `destroy_sessions_for_user`) so the surviving session stays
    correctly tracked in it. Returns the number of *other* sessions
    actually deleted.
    """
    r = get_valkey()
    user_key = _user_sessions_key(str(user_id))
    session_ids = await r.smembers(user_key)
    deleted = 0
    for session_id in session_ids:
        if session_id == keep_session_id:
            continue
        removed = await r.delete(_session_key(session_id))
        if removed:
            await r.srem(user_key, session_id)
        deleted += removed
    return deleted
