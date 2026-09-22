"""FastAPI dependency chain: session cookie -> session data -> RBAC-checked,
RLS-scoped database session.

A route that touches the database without going through `get_scoped_session`
is a defect -- it is the one place `app.actor_id`/`app.actor_role`/
`app.client_ip` get set via `SET LOCAL` for the whole request's transaction
(ADR-01), which every RLS policy and the `write_audit()` trigger (ADR-07)
depend on.
"""

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import SESSION_COOKIE_NAME
from app.core.db import async_session_factory, open_scoped_session
from app.core.sessions import SessionData, read_session
from app.models.enums import RoleCode
from app.models.role import Role
from app.models.user import User


def get_client_ip(request: Request) -> str | None:
    """No reverse proxy sits in front of this local-dev stack (unlike the
    ADR-03/ADR-06 production topology this project's sibling projects use),
    so the direct TCP peer *is* the real client -- no X-Forwarded-For /
    CF-Connecting-IP trust logic is needed here. `request.client` is None
    only in contexts FastAPI's TestClient can produce; real ASGI servers
    always populate it.
    """
    return request.client.host if request.client else None


async def get_current_session(request: Request) -> SessionData:
    """Resolves the session cookie to its Valkey-backed session data.

    Does not itself check `totp_verified` -- routes that require full
    authentication depend on `get_current_user` (below), which does.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    data = await read_session(session_id)
    if data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired or invalid")
    return data


async def get_current_user(
    session: SessionData = Depends(get_current_session),
) -> SessionData:
    """The one dependency every fully-authenticated route depends on.

    Rejects a session that has not completed mandatory TOTP verification --
    a session created by password-check-only for a role that requires TOTP
    (`app.models.enums.MANDATORY_TOTP_ROLES`) is a real Valkey entry
    (`totp_verified: False`) but cannot reach any route depending on this
    function, only the dedicated `/auth/totp/verify` endpoint.
    """
    if not session.totp_verified:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "two-factor verification required")
    return session


async def get_scoped_session(
    request: Request,
    session: SessionData = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """Opens one transaction with `app.actor_id`/`app.actor_role`/
    `app.client_ip` set via `SET LOCAL`, checks `is_active` fresh (not only
    at login -- an account an administrator just deactivated must lose
    access on its very next request, not after its session naturally
    expires), and yields the session.
    """
    user_id = uuid.UUID(session.user_id)

    async with async_session_factory() as active_check_session, active_check_session.begin():
        row = await active_check_session.execute(select(User.is_active).where(User.id == user_id))
        is_active = row.scalar_one_or_none()
        if is_active is not True:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found or inactive")

    client_ip = get_client_ip(request)
    async with open_scoped_session(
        actor_id=user_id, actor_role=session.role_code, client_ip=client_ip
    ) as db:
        yield db


def require_role(*allowed_role_codes: RoleCode):
    """FastAPI dependency factory: enforces RBAC at the application layer,
    on top of the database's own RLS defense-in-depth (ADR-02). A route
    declares `Depends(require_role(RoleCode.FINANCE_MANAGER, ...))` and
    receives the requester's own `User` row if their role is one of the
    allowed codes; otherwise the request is rejected with 403 before any
    route body executes.
    """

    async def _dependency(
        session: SessionData = Depends(get_current_user),
        db: AsyncSession = Depends(get_scoped_session),
    ) -> User:
        result = await db.execute(
            select(User).join(Role, User.role_id == Role.id).where(User.id == uuid.UUID(session.user_id))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account not found")
        if session.role_code not in {r.value for r in allowed_role_codes}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role for this action")
        return user

    return _dependency
