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

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.cookies import clear_session_cookie, set_session_cookie
from app.core.crypto import decrypt_totp_secret, encrypt_totp_secret
from app.core.db import get_db
from app.core.deps import get_client_ip, get_current_session, get_current_user
from app.core.mail import send_mail
from app.core.rate_limit import check_change_email_rate_limit, check_forgot_password_rate_limit
from app.core.security import (
    hash_backup_code,
    hash_password,
    hash_reset_token,
    hash_reset_token_dummy,
    verify_backup_code,
    verify_password,
    verify_password_dummy,
    verify_reset_token,
)
from app.core.sessions import (
    SessionData,
    create_session,
    destroy_session,
    destroy_sessions_for_user,
    mark_totp_verified,
)
from app.core.totp import generate_backup_codes, provision_secret, verify_code
from app.models.enums import MANDATORY_TOTP_ROLES, RoleCode
from app.models.password_reset_token import PasswordResetToken
from app.models.role import Role
from app.models.user import User, UserBackupCode
from app.schemas.auth import (
    ChangeEmailRequest,
    ChangeEmailResponse,
    ChangePasswordRequest,
    ConfirmEmailChangeRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    ResetPasswordRequest,
    TotpBackupCodeRequest,
    TotpEnrollConfirmRequest,
    TotpEnrollStartResponse,
    TotpVerifyRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Module 16: how long a password-reset link stays valid. Short enough
# that a link sitting unopened in an inbox is a small window, long
# enough that a real person checking their email is not racing a
# stopwatch -- the same order of magnitude every mainstream consumer
# product uses (GitHub, Google) for this exact flow.
PASSWORD_RESET_TOKEN_TTL_MINUTES = 30

# The one, fixed response every `POST /auth/forgot-password` call
# returns -- see that route's own docstring for why this must never vary
# by whether the email exists.
_FORGOT_PASSWORD_GENERIC_MESSAGE = (
    "If an account exists for this email, a password reset link has been sent."
)


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


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """Self-service password-reset request (Module 16). Unauthenticated
    by definition -- this is exactly the endpoint a locked-out user with
    no session reaches.

    **Always returns the identical generic response, regardless of
    whether the email exists.** Same anti-enumeration reasoning
    `/auth/login`'s own unknown-email path already establishes
    (`verify_password_dummy`'s own docstring): a response that varied
    by "account exists" vs "account doesn't exist" would let an
    attacker enumerate real accounts by email one guess at a time,
    for free, against an endpoint that (unlike login) requires no
    password guess at all to probe.

    **Timing parity with the real-email path (Module 16 follow-up).**
    A fixed response body is necessary but not sufficient -- this
    route's real-email path does one real Argon2id `hash()` call
    (`hash_reset_token`) plus a real SMTP send, both real work an
    attacker's clock can measure even with an identical response body.
    Live-measured before this fix: ~76ms for a real email vs ~10ms for
    a nonexistent one, an 8x/~66ms gap dominated by the hash call
    (~54ms of it in isolation) -- large enough to trivially distinguish
    the two cases by response latency alone. The unknown-email/inactive
    branch below now calls `hash_reset_token_dummy()`, a real Argon2id
    `hash()` against a fixed value, so both branches perform the same
    one-hash shape of cryptographic work -- the exact same fix login's
    own `verify_password_dummy` already applies to its own unknown-email
    path, extended here to a `hash()` call instead of a `verify()` call
    (this route commits a fresh token to storage, so there is no
    existing hash to verify against on the real-email path; the
    equivalent expensive operation is hashing the new token instead).
    The residual SMTP-send cost is deliberately not matched with a
    dummy send -- see this module's own report for why.

    **Real behavior when the email does exist:** generates a
    cryptographically random single-use token (`secrets.token_urlsafe`,
    the same primitive `create_session` already uses for session ids),
    stores only its Argon2id hash (`app.core.security.hash_reset_token`
    -- see `PasswordResetToken`'s own docstring for why never the raw
    value), and sends a real email through Mailpit containing a link
    carrying the raw token in the URL. The raw token is never persisted
    anywhere server-side after this response returns -- only its hash,
    exactly like a TOTP backup code.

    **Rate-limited per target email (Module 16 follow-up), before any
    database lookup.** This is the one endpoint in this codebase where
    an unauthenticated caller can trigger a real side effect against a
    *third party* -- mail landing in some inbox -- without proving they
    control that inbox. `check_forgot_password_rate_limit` (`app.core.
    rate_limit`) raises a real `429` after the third request for the
    same email within 15 minutes, checked against the raw requested
    string before the `SELECT` below, so the throttle threshold is
    identical whether or not the account exists -- it carries no
    account-existence signal of its own, preserving this route's own
    anti-enumeration guarantee.
    """
    await check_forgot_password_rate_limit(body.email)

    result = await db.execute(
        select(User).where(User.email == body.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if user is None:
        hash_reset_token_dummy()
        return ForgotPasswordResponse(message=_FORGOT_PASSWORD_GENERIC_MESSAGE)

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES
    )
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(raw_token),
            expires_at=expires_at,
        )
    )
    await db.flush()

    reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={raw_token}"
    await send_mail(
        to_address=user.email,
        subject="Reset your Sirius password",
        body=(
            "A password reset was requested for your Sirius account.\n\n"
            f"Reset your password using this link: {reset_link}\n\n"
            f"This link expires in {PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes "
            "and can only be used once.\n\n"
            "If you did not request this, you can safely ignore this email."
        ),
    )

    return ForgotPasswordResponse(message=_FORGOT_PASSWORD_GENERIC_MESSAGE)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Completes a self-service password reset, **or an admin-created
    account's first-ever activation (Module 17)** -- both are the exact
    same redemption code, deliberately. Unauthenticated by definition --
    the raw token from the email link is the caller's entire proof of
    identity here, exactly as a TOTP backup code is for
    `/auth/totp/verify-backup-code`.

    **Token lookup is by hash comparison against every un-used,
    unexpired, password-type token row** (`new_email IS NULL` --
    Module 17 extended this table to also carry email-change tokens,
    which are redeemed only by the distinct
    `POST /auth/confirm-email-change`; this filter keeps the two
    token kinds from ever being redeemable through each other's
    endpoint), the same shape `totp_verify_backup_code` already uses
    for backup codes (there is no way to look up a row by its own hash
    directly with Argon2id's own random salt -- each `_hasher.verify`
    call is against one candidate row). In practice this table holds at
    most a handful of live rows per user at once, never enough for this
    linear scan to matter.

    **Real, distinct rejection reasons** -- never a generic "invalid
    token" for every failure mode, matching this module's own
    requirement:
    - No matching, unexpired, unused token hash at all: "invalid or
      expired reset token" (deliberately not distinguishing "wrong
      token" from "expired" from "already used" *at the query level*,
      since a wrong-token guess and an expired real token look
      identical from the caller's side by design -- but an
      already-used token *is* distinguished, next).
    - A token that matches by hash but has already been used
      (`used_at IS NOT NULL`): a distinct, specific "this reset link
      has already been used" -- found separately from the main query
      (which only selects `used_at IS NULL` rows) specifically so this
      case gets its own real message rather than silently falling into
      the generic "invalid or expired" bucket alongside a token that
      never existed at all.

    **Stamps `User.activated_at` if this is the account's first-ever
    successful redemption** (Module 17) -- `activated_at is None` is
    checked *before* the write, so an ordinary later forgot-password
    reset against an already-activated account never touches this
    column again; it only ever transitions once, from `NULL` to a real
    timestamp, on whichever redemption -- the original welcome token or
    a subsequent forgot-password token, doesn't matter which -- happens
    to be the account's first.

    **Force-logs-out any active session for this account**, via
    `destroy_sessions_for_user` -- the same reasoning
    `app.routers.users.reset_totp` already established for an admin-
    triggered TOTP reset (Module 15's own follow-up): a password reset
    exists because the account holder no longer trusts their current
    credential (forgotten, or possibly compromised), and a session that
    authenticated with the *old* password should not be assumed safe
    to leave running just because it happened to be open at the moment
    of reset. For a first-activation redemption specifically, there is
    no prior session to kill (an unactivated account's unguessable
    password hash makes login structurally impossible until this exact
    call succeeds), so this is a genuine no-op in that case, not a
    special-cased skip.
    """
    incoming_hash_candidates = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.new_email.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    matched: PasswordResetToken | None = None
    for candidate in incoming_hash_candidates.scalars().all():
        if verify_reset_token(body.token, candidate.token_hash):
            matched = candidate
            break

    if matched is None:
        # Distinguish "already used" from "never existed / expired" --
        # see this route's own docstring for why only this one case
        # gets a separate, real message.
        already_used_result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.used_at.is_not(None),
                PasswordResetToken.new_email.is_(None),
            )
        )
        for candidate in already_used_result.scalars().all():
            if verify_reset_token(body.token, candidate.token_hash):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "this reset link has already been used"
                )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset token")

    user_result = await db.execute(select(User).where(User.id == matched.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset token")

    user.password_hash = hash_password(body.new_password)
    if user.activated_at is None:
        user.activated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    matched.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    await destroy_sessions_for_user(user.id)


@router.post("/change-email", response_model=ChangeEmailResponse)
async def change_email(
    body: ChangeEmailRequest,
    session: SessionData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChangeEmailResponse:
    """Self-service email-change request (Module 17). Requires a fully
    authenticated session (`get_current_user`, the same dependency
    `change_password` uses) -- unlike the password-reset/welcome flows,
    there is no "locked out, no session" scenario for this action; the
    account holder is, by definition, already signed in to request it.

    **Does not change `User.email` at all.** Only a real, single-use,
    hashed, expiring token is issued -- through the exact same
    `PasswordResetToken` table Module 16 built, with `new_email` set
    (see that model's own docstring for why this field is what
    distinguishes an email-change token from a password-type one) --
    and a real confirmation email is sent through Mailpit to the
    **new** address, not the current one. The account continues
    authenticating with its current email, completely unaffected, until
    `POST /auth/confirm-email-change` is called with that link's token
    (see that route's own docstring for what actually changes and
    when).

    **Silently does not reveal whether `new_email` is already taken by
    a different account.** If it is, this call still returns the same
    success response and still issues a token -- but a token whose
    `new_email` collides with an existing account's email at
    confirmation time is rejected then, not now (see
    `confirm_email_change`'s own docstring). Checking availability here
    and returning a different response for "already taken" would let
    any authenticated caller enumerate which arbitrary addresses are
    registered accounts, the exact same anti-enumeration reasoning
    `POST /auth/forgot-password` already established for an
    *unauthenticated* caller -- this endpoint closes the same gap for
    an *authenticated* one probing on someone else's behalf.

    **Rate-limited per target `new_email` (Module 17 follow-up), before
    any write.** Being authenticated only proves who the *caller* is --
    it does not prove the caller owns `new_email`, so this endpoint has
    the identical third-party-mail-bombing exposure
    `POST /auth/forgot-password` already has, and gets the identical
    fix: `check_change_email_rate_limit` (`app.core.rate_limit`) raises
    a real `429` after the third request aimed at the same target
    address within 15 minutes, regardless of which authenticated
    account is doing the requesting -- see that function's own
    docstring for why it is keyed by the target address, not the
    caller's account.
    """
    await check_change_email_rate_limit(body.new_email)

    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found")

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES
    )
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(raw_token),
            expires_at=expires_at,
            new_email=body.new_email,
        )
    )
    await db.flush()

    confirm_link = f"{settings.FRONTEND_BASE_URL}/confirm-email-change?token={raw_token}"
    await send_mail(
        to_address=body.new_email,
        subject="Confirm your new Sirius email address",
        body=(
            "A request was made to change the email address on a Sirius "
            f"account to this address ({body.new_email}).\n\n"
            f"Confirm this change using this link: {confirm_link}\n\n"
            f"This link expires in {PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes "
            "and can only be used once. Your account will keep signing in "
            "with its current email until you confirm.\n\n"
            "If you did not request this, you can safely ignore this email -- "
            "your account's email address will not change."
        ),
    )

    return ChangeEmailResponse(
        message="Confirmation email sent to the new address. Your login email "
        "will not change until you confirm."
    )


@router.post("/confirm-email-change", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email_change(
    body: ConfirmEmailChangeRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Completes a self-service email change (Module 17). Unauthenticated
    by definition -- the raw token from the confirmation email, sent to
    the *new* address, is the caller's entire proof they control that
    mailbox; nothing else authenticates this request, the same shape
    `POST /auth/reset-password` already establishes for password
    tokens.

    **Token lookup is by hash comparison against every un-used,
    unexpired, email-change token row** (`new_email IS NOT NULL` --
    the mirror-image filter of `reset_password`'s own `IS NULL`, so the
    two token kinds stay mutually exclusive at redemption time). Same
    real, distinct rejection reasons as password-token redemption:
    "invalid or expired reset token" for no match, a separate
    "this reset link has already been used" for a token that matches by
    hash but was already redeemed.

    **Checks `new_email` availability now, not at request time** (see
    `change_email`'s own docstring for why the *request* side stays
    silent about it) -- if some other account has taken that email in
    the interval between request and confirmation, this call rejects
    with a real, specific reason rather than silently overwriting into
    a collision the database's own `uq_user_email` constraint would
    reject anyway with a much less useful integrity-error message.

    **Only `User.email` changes here.** No session is force-logged-out
    (contrast `reset_password`'s own session kill) -- the account's
    existing sessions authenticated against its identity at the time
    they were created and remain exactly as valid as they were before
    this call; only the *email* used for future logins changes, not
    the account's current authenticated state.
    """
    incoming_hash_candidates = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.new_email.is_not(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    matched: PasswordResetToken | None = None
    for candidate in incoming_hash_candidates.scalars().all():
        if verify_reset_token(body.token, candidate.token_hash):
            matched = candidate
            break

    if matched is None:
        already_used_result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.used_at.is_not(None),
                PasswordResetToken.new_email.is_not(None),
            )
        )
        for candidate in already_used_result.scalars().all():
            if verify_reset_token(body.token, candidate.token_hash):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "this confirmation link has already been used"
                )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired confirmation token")

    user_result = await db.execute(select(User).where(User.id == matched.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired confirmation token")

    assert matched.new_email is not None  # guaranteed by the query filter above
    collision = (
        await db.execute(
            select(User.id).where(User.email == matched.new_email, User.id != user.id)
        )
    ).scalar_one_or_none()
    if collision is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this email address is now in use by another account"
        )

    user.email = matched.new_email
    matched.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
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

    **`pending_email` (Module 17) -- decision: an in-flight,
    unconfirmed email change is shown, not hidden.** If this account
    has a real, unexpired, unused email-change token row, its
    `new_email` is surfaced here so `ProfilePage` can display "pending
    change to X." The alternative (staying silent until confirmation)
    would leave the account holder with no way to tell, short of
    checking the new inbox themselves, whether their own change request
    actually registered -- indistinguishable from the request having
    silently failed. Showing it costs nothing security-relevant: this
    is the account's own authenticated session reading back its own
    pending state, not a third party learning anything about a
    different account.
    """
    user_id = uuid.UUID(session.user_id)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found")

    pending_result = await db.execute(
        select(PasswordResetToken.new_email)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.new_email.is_not(None),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    pending_email = pending_result.scalar_one_or_none()

    return MeResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_code=session.role_code,
        totp_enabled=user.totp_enabled,
        pending_email=pending_email,
    )


__all__ = ["router", "hash_password", "get_client_ip"]
