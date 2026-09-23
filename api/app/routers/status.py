"""Status-transition endpoint: moves an applicant from its current status
to a requested one, enforcing the explicit transition table
(`app.services.status_transitions`), never a free-form status write.

**RBAC.** `SUPER_ADMIN`, `ADMISSIONS_MANAGER`, and `ADMISSIONS_COUNSELOR`
may call this endpoint at all -- `FINANCE_STAFF`/`FINANCE_MANAGER`/
`AUDITOR` can see applicant data for reconciliation (ADR-03) but have no
legitimate reason to drive the admissions pipeline itself, so they are
excluded here even though the RLS `applicant` policy grants them read
visibility. Within those three permitted roles, RLS (ADR-03) does the rest
of the scoping automatically: an `ADMISSIONS_COUNSELOR`'s read/write only
ever matches a row when `assigned_counselor_id` is their own id, so
attempting to transition another counselor's applicant finds no row at
all and this endpoint reports 404 rather than 403 -- consistent with the
RLS fail-closed design (module 01): the applicant is invisible to this
actor, not merely off-limits.

**Why 422, never 500, for an invalid transition.** A transition not in
`ALLOWED_TRANSITIONS` is a client input error (the requested destination is
not reachable from the applicant's current state), not a server fault --
`HTTP_422_UNPROCESSABLE_ENTITY` with a message naming both the current and
requested status, so the caller can see exactly which transition was
rejected rather than a generic "bad request."

**Why the finance_record creation is not application code here.** Migration
`0007_finance_record_auto_create` added a database trigger,
`applicant_create_finance_record()`, firing `AFTER UPDATE OF
current_status ON applicant WHEN (NEW.current_status = 'ADMISSION_TAKEN'
...)`. This endpoint's `UPDATE applicant SET current_status = ...` is the
only write it performs against `applicant`; the trigger does the rest,
without this router importing or calling anything finance-related at all
-- confirmed against the live stack (see the module-02 report), including
the counselor-driven path, which surfaced and fixed a real RLS/`ON
CONFLICT` interaction bug in that trigger (migration 0007's own docstring
has the full account).

**One transaction, not two.** `require_role_session` (app.core.deps)
yields `(user, db)` from the *same* RLS-scoped transaction the role check
ran under, so the applicant read, the status `UPDATE`, and the
`application_status_event` insert below all happen in the one transaction
`get_scoped_session` opened for this request -- not a second, separately-
scoped session reopened inside the route body.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.models.applicant import Applicant
from app.models.application_status_event import ApplicationStatusEvent
from app.models.enums import RoleCode
from app.models.user import User
from app.schemas.status import StatusTransitionRequest, StatusTransitionResponse
from app.services.status_transitions import is_transition_allowed

router = APIRouter(prefix="/applicants", tags=["status"])


@router.post("/{applicant_id}/status", response_model=StatusTransitionResponse)
async def transition_applicant_status(
    applicant_id: uuid.UUID,
    body: StatusTransitionRequest,
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(
            RoleCode.SUPER_ADMIN, RoleCode.ADMISSIONS_MANAGER, RoleCode.ADMISSIONS_COUNSELOR
        )
    ),
) -> StatusTransitionResponse:
    user, db = user_and_db

    result = await db.execute(select(Applicant).where(Applicant.id == applicant_id))
    applicant = result.scalar_one_or_none()
    if applicant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "applicant not found")

    from_status = applicant.current_status
    to_status = body.to_status

    if not is_transition_allowed(from_status, to_status):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"invalid status transition: {from_status.value} -> {to_status.value}",
        )

    applicant.current_status = to_status
    event = ApplicationStatusEvent(
        applicant_id=applicant.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=user.id,
        note=body.note,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    return StatusTransitionResponse(
        applicant_id=applicant.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=user.id,
        created_at=event.created_at,
    )
