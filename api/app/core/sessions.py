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


async def create_session(user_id: uuid.UUID, role_code: str, totp_verified: bool) -> str:
    session_id = secrets.token_urlsafe(32)
    data = SessionData(user_id=str(user_id), role_code=role_code, totp_verified=totp_verified)
    payload = encrypt_session_payload(json.dumps(asdict(data)))
    r = get_valkey()
    await r.set(_session_key(session_id), payload, ex=SESSION_TTL_SECONDS)
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


async def destroy_session(session_id: str) -> None:
    r = get_valkey()
    await r.delete(_session_key(session_id))
