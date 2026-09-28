"""Request schema for manual single-applicant creation (Module 19,
`POST /applicants` -- `api/app/routers/applicant_create.py`).

The response reuses `app.schemas.reads.ApplicantDetail` verbatim -- the
same shape `GET /applicants/{id}` already returns -- rather than a new,
parallel response model, since a freshly-created applicant has exactly
the same fields a freshly-read one does.
"""

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.core.field_limits import MAX_FIELD_LENGTH


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

    **`max_length=MAX_FIELD_LENGTH` (255) on every free-text field
    (Module 21 audit finding, fixed here).** Before this fix, no
    schema anywhere in this codebase bounded a text field's length at
    all -- confirmed live: a genuine `10,000`-character `full_name` was
    accepted with a real `201`, stored in full (`character varying`
    with no declared limit at the Postgres column level either), and
    then broke the `ApplicantsPage` table's own layout when rendered
    (the row's text overflowed its cell with no truncation, pushing
    every later column off-screen -- see that page's own `Table.Td`
    styling for the matching frontend fix). `255` is not an arbitrary
    round number: it is the conventional ceiling for a "short text"
    field across this stack's likely eventual index/display needs and
    comfortably exceeds any real person's name, degree program, or
    intake-cycle label (the longest real seed value in this database
    is well under 30 characters) while still being generous enough
    that no legitimate input is ever at risk of rejection.

    **Correction (Module 21 follow-up, not the original claim): this
    schema does NOT guard the write side of every applicant-creation
    path -- it only guards this one endpoint.** The original version
    of this docstring claimed fixing only this endpoint was sufficient
    because "every other applicant-creation path -- including Excel
    import -- ultimately funnels through the same `applicant` table
    that this schema alone directly guards on the write side." That
    claim was false, and confirmed false live: `POST /import/
    applicants` never instantiates `ApplicantCreateRequest` at all --
    it builds `Applicant(...)` ORM rows directly from
    `app.services.excel_import.ParsedRow`, parsed straight out of the
    uploaded spreadsheet, completely bypassing this schema. A real
    `.xlsx` with a 5,000-character `Full Name` cell was accepted by
    the real import endpoint with `rejected_count: 0` and landed in
    the database in full. That path is now fixed independently, at
    parse time in `app.services.excel_import.parse_workbook` (rejected
    per-row, the same way a missing `full_name`/`email` already is),
    and a database-level `CHECK` constraint (migration
    `0014_applicant_field_length`) now backstops every write path to
    `applicant`'s own text columns -- this schema, the import path,
    and any future or direct-SQL write neither of them ever sees --
    the same defense-in-depth shape the negative-payment-amount fix
    already established. `UserCreateRequest.full_name`,
    `ChangeNameRequest.full_name`, `PaymentClaimSubmitRequest.
    reference_number`, and `PaymentClaimResolveRequest.note` remain
    genuinely out of scope for this pass (a different table, not
    `applicant`) -- see `reports/module-21-edge-case-audit.md`'s own
    input-boundaries section and its "Follow-up verification" section
    for the full account of what is now covered and what still isn't.
    """

    full_name: str = Field(min_length=1, max_length=MAX_FIELD_LENGTH)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=MAX_FIELD_LENGTH)
    program: str = Field(min_length=1, max_length=MAX_FIELD_LENGTH)
    intake_cycle: str = Field(min_length=1, max_length=MAX_FIELD_LENGTH)
    assigned_counselor_id: uuid.UUID | None = None
