"""Request schema for manual single-applicant creation (Module 19,
`POST /applicants` -- `api/app/routers/applicant_create.py`).

The response reuses `app.schemas.reads.ApplicantDetail` verbatim -- the
same shape `GET /applicants/{id}` already returns -- rather than a new,
parallel response model, since a freshly-created applicant has exactly
the same fields a freshly-read one does.
"""

import uuid

from pydantic import BaseModel, EmailStr


class ApplicantCreateRequest(BaseModel):
    """`POST /applicants` (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/
    `ADMISSIONS_COUNSELOR` -- the same three roles
    `app.routers.status.transition_applicant_status` already owns).

    **`assigned_counselor_id` is optional and role-dependent -- see the
    route's own docstring for the full reasoning:**

    - `ADMISSIONS_COUNSELOR`: may be omitted (auto-assigned to the
      caller themselves) or sent equal to the caller's own id (same
      result); any *other* counselor's id is rejected with 422.
    - `SUPER_ADMIN`/`ADMISSIONS_MANAGER`: may be omitted (created
      unassigned) or sent as any existing, active `ADMISSIONS_COUNSELOR`
      account's id.

    No `current_status` field -- this endpoint decides the initial
    status itself (`APPLIED`; see the route's own docstring), the same
    "the endpoint decides, the caller doesn't get to override it" rule
    `app.routers.import_.import_applicants` already applies to
    `IMPORTED`. No `import_batch_id` field either -- always `NULL` for
    a manually-created applicant, by construction, never client-supplied.
    """

    full_name: str
    email: EmailStr
    phone: str | None = None
    program: str
    intake_cycle: str
    assigned_counselor_id: uuid.UUID | None = None
