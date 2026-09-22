"""Minimal role-gated routes demonstrating `require_role` and
`get_scoped_session` end-to-end against a live database, since this
module's own status-transition and payment-workflow endpoints are
deferred to the next module (see the module prompt) and RBAC needs at
least one real route to be verified against, not only reviewed as code.
"""

from fastapi import APIRouter, Depends

from app.core.deps import require_role
from app.models.enums import RoleCode
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(
    user: User = Depends(
        require_role(RoleCode.SUPER_ADMIN, RoleCode.ADMISSIONS_MANAGER, RoleCode.AUDITOR)
    ),
) -> dict[str, str]:
    """Reachable only by SUPER_ADMIN, ADMISSIONS_MANAGER, or AUDITOR --
    exercises the full session -> RBAC -> RLS-scoped-session chain
    (`require_role` depends on both `get_current_user`, which enforces
    mandatory TOTP, and `get_scoped_session`, which enforces `is_active`
    fresh and sets the RLS GUCs) against a real request, not a unit test
    double.
    """
    return {"ok": "true", "user_id": str(user.id)}
