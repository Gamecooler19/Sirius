"""User administration (Module 15): list/create/update accounts, and reset
a mandatory-TOTP account's enrollment for the lost-device case.

**Why RBAC only, no new RLS.** `role`/`user`/`user_backup_code` are the
identity axis this project's own ADR-03 already carves out as a
deliberate, structural exception to row-level security: "Login must look
up a user by email before any session (and therefore any
`app.actor_role`) exists, which makes an RLS-scoped `user` table
structurally impossible to authenticate against." Every route below
reuses that exact precedent -- `require_role(RoleCode.SUPER_ADMIN)`
(`app.core.deps`) is the entire access-control story, layered on top of
`get_scoped_session`'s own unconditional `is_active` check (any caller,
including a `SUPER_ADMIN`, must themselves be active to reach any
authenticated route at all). No RLS policy is added, changed, or removed
by this module; `user` remains exactly as unscoped as ADR-03 already
decided it should be, for the same structural reason.

**Why `POST /users` always creates `totp_enabled=False`.** `User.totp_enabled`
already `server_default`s to `false` (Module 01's own migration), and
this endpoint does not override that default -- it is not merely
convenient, it is the entire mechanism by which a mandatory-TOTP role's
freshly admin-created account goes through the real, existing enrollment
flow (`POST /auth/totp/enroll/start` + `/confirm`) on its very first
login, with zero new authentication-flow code written by this module.
`POST /auth/login` already branches on `totp_enabled` (Module 01's own
`totp_enrollment_required` calculation); a new `SUPER_ADMIN`/
`FINANCE_STAFF`/`FINANCE_MANAGER` account created here is
indistinguishable, from that endpoint's point of view, from a role
enrolled by hand in Module 11 -- both have `totp_enabled=False` until a
real device scans a real QR code.

**Self-lockout guard on `PATCH /users/{id}`.** A `SUPER_ADMIN` changing
their own `role_code` away from `SUPER_ADMIN`, or their own `is_active`
to `False`, through this endpoint is rejected with 422 before any write
-- the same class of footgun this project's payment-claim maker-checker
guard already exists to prevent (`app.routers.payment_claim`'s own
docstring: "rejected at the application layer... not left to surface as
[an] unhandled... 500"), applied here to a different, but structurally
identical, self-inflicted-lockout risk: the one difference from
maker-checker is that a self-demotion isn't rejected because *someone
else* should have done it (there is no maker/checker split for user
administration), but because succeeding would strip the only account
capable of reversing the mistake, with no recovery path at the
application layer at all. Every other `SUPER_ADMIN` (or the same one,
after logging back in with a role that still has access) can still patch
this account normally -- the guard is scoped to "acting on your own
account," not "acting on any `SUPER_ADMIN` account."
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.core.security import hash_password
from app.core.sessions import destroy_sessions_for_user
from app.models.enums import RoleCode
from app.models.role import Role
from app.models.user import User
from app.schemas.users import (
    UserCreateRequest,
    UserListResponse,
    UserSummary,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


def _to_summary(user: User, role_code: str) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_code=role_code,
        is_active=user.is_active,
        totp_enabled=user.totp_enabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.get("", response_model=UserListResponse)
async def list_users(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN)
    ),
) -> UserListResponse:
    """Same `limit`/`offset` pagination shape every other list endpoint
    in this codebase uses (`applicants_read.list_applicants`,
    `payment_claim.list_payment_claims`, `import_batches_read`) -- no
    invented convention for this one endpoint.
    """
    _, db = user_and_db

    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    rows = (
        await db.execute(
            select(User, Role.code)
            .join(Role, User.role_id == Role.id)
            .order_by(User.created_at.asc(), User.id.asc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return UserListResponse(
        items=[_to_summary(u, role_code) for u, role_code in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN)
    ),
) -> UserSummary:
    """Creates a new account, active by construction
    (`User.is_active`'s own `server_default`), `totp_enabled=False`
    always -- see this module's own docstring for why that second
    default is the entire mechanism that makes a mandatory-TOTP role's
    new account go through the real enrollment flow on first login. The
    password is hashed via the exact same `hash_password` (Argon2id)
    every other account's credential goes through -- no separate,
    admin-only hashing path.
    """
    _, db = user_and_db

    existing = (
        await db.execute(select(User.id).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a user with this email already exists")

    role_row = (
        await db.execute(select(Role).where(Role.code == body.role_code.value))
    ).scalar_one_or_none()
    if role_row is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown role")

    user = User(
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role_id=role_row.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return _to_summary(user, body.role_code.value)


@router.patch("/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    actor_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN)
    ),
) -> UserSummary:
    """Updates `role_code` and/or `is_active` on an existing account.

    **Self-lockout guard**, checked before any write: a `SUPER_ADMIN`
    patching their own account (`user_id == actor.id`) is rejected with
    422 if the patch would change `role_code` away from `SUPER_ADMIN` or
    set `is_active` to `False` -- see this module's own docstring for the
    full reasoning. `model_fields_set` (not a plain `is not None` check)
    decides whether `is_active` was actually sent, so an update that only
    touches `role_code` cannot be misread as also demoting
    `is_active` to `None`/omitted-as-false.
    """
    actor, db = actor_and_db

    result = await db.execute(
        select(User, Role.code).join(Role, User.role_id == Role.id).where(User.id == user_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    user, current_role_code = row

    is_self = user.id == actor.id
    wants_role_change = "role_code" in body.model_fields_set and body.role_code is not None
    wants_deactivate = "is_active" in body.model_fields_set and body.is_active is False

    if is_self and wants_role_change and body.role_code.value != RoleCode.SUPER_ADMIN.value:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cannot change your own role away from SUPER_ADMIN through this endpoint "
            "(self-lockout guard)",
        )
    if is_self and wants_deactivate:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cannot deactivate your own account through this endpoint (self-lockout guard)",
        )

    new_role_code = current_role_code
    if wants_role_change:
        role_row = (
            await db.execute(select(Role).where(Role.code == body.role_code.value))
        ).scalar_one_or_none()
        if role_row is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown role")
        user.role_id = role_row.id
        new_role_code = body.role_code.value

    if "is_active" in body.model_fields_set and body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()
    await db.refresh(user)

    return _to_summary(user, new_role_code)


@router.post("/{user_id}/reset-totp", response_model=UserSummary)
async def reset_totp(
    user_id: uuid.UUID,
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN)
    ),
) -> UserSummary:
    """Clears the stored TOTP secret and `totp_enabled`, for the
    lost-device case (a mandatory-TOTP user whose authenticator app/phone
    is gone, and who has exhausted or lost their backup codes) -- a
    scenario this project's auth flow had no recovery path for at all
    before this module. Does **not** delete existing `UserBackupCode`
    rows for this user; a fresh `POST /auth/totp/enroll/start` on that
    account's next login already deletes and reissues them itself
    (`app.routers.auth.totp_enroll_start`'s own docstring: "Re-calling
    `start`... overwrites the prior unconfirmed secret/codes"), so this
    endpoint does not need to duplicate that cleanup.

    After this call, the account's next `POST /auth/login` sees
    `totp_enabled=False` again and receives `totp_enrollment_required:
    true` in the response, driving the client through the real
    enrollment flow (`/auth/totp/enroll/start` + `/confirm`) exactly as
    if this were the account's very first login -- not the
    `/auth/totp/verify` flow a still-enrolled account would hit.

    **Also force-logs-out any currently active session for this account
    (Module 15 follow-up).** The threat model this endpoint exists for is
    a lost or stolen device -- if that device (or whoever now holds it)
    also still has a live, already-TOTP-verified browser session open,
    clearing the *database* secret alone would not touch that session at
    all: `require_role_session` and `get_current_user` only ever read
    `role_code`/`totp_verified` out of the Valkey session payload, never
    re-check `user.totp_enabled` per request, so a session that was
    already fully authenticated before the reset would keep working,
    completely undisturbed, until it expired on its own (up to the full
    12-hour `SESSION_TTL_SECONDS`) or the user logged out voluntarily.
    For an endpoint whose entire reason to exist is "I no longer trust
    this account's second factor," leaving a live, already-past-that-
    factor session running is the exact gap the endpoint claims to
    close. `destroy_sessions_for_user` (`app.core.sessions`) deletes
    every Valkey session this user currently has open via the
    `user_sessions:{user_id}` index `create_session` maintains -- a
    real, if rare, false-positive cost is a device the admin did *not*
    intend to also sign out (the legitimate user, re-logging in on a
    new phone, who is simultaneously still signed in on a laptop) also
    getting logged out; accepted deliberately, since a lost/stolen
    device serious enough to need a TOTP reset should not leave any
    session assumed safe by default.
    """
    _, db = user_and_db

    result = await db.execute(
        select(User, Role.code).join(Role, User.role_id == Role.id).where(User.id == user_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    user, role_code = row

    user.totp_secret_encrypted = None
    user.totp_enabled = False
    await db.flush()
    await db.refresh(user)

    await destroy_sessions_for_user(user.id)

    return _to_summary(user, role_code)
