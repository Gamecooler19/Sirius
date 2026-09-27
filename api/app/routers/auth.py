"""Session-based authentication: login (argon2id password check), mandatory
TOTP enrollment/verification for roles that require it, and logout.

**Login flow.**
1. `POST /auth/login`: verify email+password. On success, create a Valkey
   session with `totp_verified` pre-set to whatever it should start as:
   - Role not in `MANDATORY_TOTP_ROLES`: `totp_verified=True` immediately --
     TOTP is not required for this role, so there is nothing to wait for.
   - Role in `MANDATORY_TOTP_ROLES`, TOTP already enrolled
     (`user.totp_enabled=True`): `totp_verified=False` -- the session exists
     but cannot reach any protected route until `/auth/totp/verify` succeeds.
   - Role in `MANDATORY_TOTP_ROLES`, TOTP not yet enrolled: same as above,
     `totp_verified=False`; the client is told (`totp_enrollment_required`)
     to drive the user through `/auth/totp/enroll/start` +
     `/auth/totp/enroll/confirm` before `/auth/totp/verify` becomes usable
     for future logins.
2. The session cookie is set (httpOnly/SameSite=Strict, Secure per
   settings) covering this TOTP-pending state too -- there is exactly one
   cookie for the whole login-to-fully-authenticated flow, not a separate
   pre-auth cookie, since Valkey's own `totp_verified` flag is what actually
   gates access (`app.core.deps.get_current_user`), not cookie possession.

**Why enrollment start/confirm both require an existing (TOTP-pending)
session rather than a fresh unauthenticated call.** Enrollment provisions a
brand new TOTP secret for *this* account; the only way to know which account
is the same login-identity check every other protected action uses.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.cookies import clear_session_cookie, set_session_cookie
from app.core.crypto import decrypt_totp_secret, encrypt_totp_secret
from app.core.db import get_db
from app.core.deps import get_client_ip, get_current_session, get_current_user
from app.core.security import (
    hash_backup_code,
    hash_password,
    verify_backup_code,
    verify_password,
    verify_password_dummy,
)
from app.core.sessions import SessionData, create_session, destroy_session, mark_totp_verified
from app.core.totp import generate_backup_codes, provision_secret, verify_code
from app.models.enums import MANDATORY_TOTP_ROLES, RoleCode
from app.models.role import Role
from app.models.user import User, UserBackupCode
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    TotpBackupCodeRequest,
    TotpEnrollConfirmRequest,
    TotpEnrollStartResponse,
    TotpVerifyRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    result = await db.execute(
        select(User, Role.code).join(Role, User.role_id == Role.id).where(User.email == body.email)
    )
    row = result.first()

    if row is None:
        verify_password_dummy(body.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    user, role_code = row

    if not user.is_active:
        verify_password_dummy(body.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")

    totp_mandatory = RoleCode(role_code) in MANDATORY_TOTP_ROLES
    totp_verified_initial = not totp_mandatory

    session_id = await create_session(
        user_id=user.id, role_code=role_code, totp_verified=totp_verified_initial
    )
    set_session_cookie(response, session_id)

    return LoginResponse(
        user_id=user.id,
        role_code=role_code,
        totp_required=totp_mandatory,
        totp_enrollment_required=totp_mandatory and not user.totp_enabled,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    from app.core.cookies import SESSION_COOKIE_NAME

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await destroy_session(session_id)
    clear_session_cookie(response)


@router.post("/totp/enroll/start", response_model=TotpEnrollStartResponse)
async def totp_enroll_start(
    session: SessionData = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> TotpEnrollStartResponse:
    """Generates a fresh TOTP secret and ten backup codes for the
    session's own user, and stores both immediately (secret encrypted,
    backup codes hashed) -- `enroll/confirm` only verifies the first live
    code before flipping `totp_enabled`, it does not re-provision.
    Re-calling `start` before `confirm` overwrites the prior unconfirmed
    secret/codes, which is intentional: an abandoned enrollment attempt
    should not linger as a dangling, never-verified secret.
    """
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found")

    raw_secret, uri = provision_secret(user.email)
    user.totp_secret_encrypted = encrypt_totp_secret(raw_secret)
    user.totp_enabled = False

    await db.execute(
        UserBackupCode.__table__.delete().where(UserBackupCode.user_id == user_id)
    )
    backup_codes = generate_backup_codes()
    for code in backup_codes:
        db.add(UserBackupCode(user_id=user_id, code_hash=hash_backup_code(code)))

    await db.flush()

    return TotpEnrollStartResponse(provisioning_uri=uri, backup_codes=backup_codes)


@router.post("/totp/enroll/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def totp_enroll_confirm(
    body: TotpEnrollConfirmRequest,
    request: Request,
    session: SessionData = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Verifies the first live code against the freshly provisioned secret
    before flipping `totp_enabled=True` -- this proves the user actually
    scanned the QR code into a working authenticator, not merely that a
    secret exists in the database.
    """
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.totp_secret_encrypted is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no pending TOTP enrollment")

    raw_secret = decrypt_totp_secret(user.totp_secret_encrypted)
    if not verify_code(raw_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid TOTP code")

    user.totp_enabled = True
    await db.flush()

    session_id = request.cookies.get("sirius_session")
    if session_id:
        await mark_totp_verified(session_id)


@router.post("/totp/verify", status_code=status.HTTP_204_NO_CONTENT)
async def totp_verify(
    body: TotpVerifyRequest,
    request: Request,
    session: SessionData = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.totp_enabled or user.totp_secret_encrypted is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOTP not enrolled for this account")

    raw_secret = decrypt_totp_secret(user.totp_secret_encrypted)
    if not verify_code(raw_secret, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid TOTP code")

    session_id = request.cookies.get("sirius_session")
    if session_id:
        await mark_totp_verified(session_id)


@router.post("/totp/verify-backup-code", status_code=status.HTTP_204_NO_CONTENT)
async def totp_verify_backup_code(
    body: TotpBackupCodeRequest,
    request: Request,
    session: SessionData = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Consumes exactly one of the ten single-use backup codes in place of
    a live TOTP code -- e.g. the user lost their authenticator device. Each
    code works once: `used_at` is stamped the instant it verifies, and every
    future attempt with the same code fails the `used_at IS NULL` filter
    below even if the plaintext code is somehow guessed correctly again.
    """
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(
        select(UserBackupCode).where(
            UserBackupCode.user_id == user_id, UserBackupCode.used_at.is_(None)
        )
    )
    candidates = result.scalars().all()

    matched = None
    for candidate in candidates:
        if verify_backup_code(body.backup_code, candidate.code_hash):
            matched = candidate
            break

    if matched is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or already-used backup code")

    from sqlalchemy import func

    matched.used_at = func.now()
    await db.flush()

    session_id = request.cookies.get("sirius_session")
    if session_id:
        await mark_totp_verified(session_id)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    session: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Self-service password change (Module 15). Depends on
    `get_current_user`, not `get_current_session` -- unlike `/me`, this is
    a genuine mutation of a security-sensitive credential, so it requires
    a fully authenticated session (mandatory TOTP already verified for a
    role that requires it), not merely a TOTP-pending one.

    **Identity is sourced exclusively from the session, never the request
    body** -- there is no `user_id` field on `ChangePasswordRequest` at
    all (see that schema's own docstring), the same "trust the session"
    rule `submitted_by` on payment claims already established. This
    endpoint can only ever change the calling session's own password.

    **Current-password verification reuses `verify_password` -- the exact
    same Argon2id path `/auth/login` uses** (`app.core.security`), not a
    second, independently-written comparison. A wrong current password is
    rejected with the real, specific error text ("current password is
    incorrect"), not the generic "invalid email or password" `/auth/login`
    uses for its own, different reason (avoiding a user-enumeration
    timing/response-shape oracle on an *unauthenticated* endpoint) --
    that reasoning does not apply here, since the caller is already a
    verified, authenticated session and already knows their own email;
    withholding *which* field was wrong on an authenticated self-service
    action would only be user-hostile, not a real security improvement.
    """
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found")

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "current password is incorrect")

    user.password_hash = hash_password(body.new_password)
    await db.flush()


@router.get("/me", response_model=MeResponse)
async def me(
    session: SessionData = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Deliberately depends on `get_current_session`, not `get_current_user`
    -- a TOTP-pending session must still be able to call `/me` to find out
    which account it belongs to and whether enrollment is needed, even
    though it cannot reach any RLS-scoped business route yet.
    """
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found")

    return MeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_code=session.role_code,
        totp_enabled=user.totp_enabled,
    )


__all__ = ["router", "hash_password", "get_client_ip"]
