"""applicant_field_length

Revision ID: 0014_applicant_field_length
Revises: 0013_positive_amount
Create Date: 2026-09-28

Module 21 follow-up verification finding, fixed here: `applicant`'s
own text columns (`full_name`, `email`, `phone`, `program`,
`intake_cycle`) had no length bound at the database level at all --
`character varying` with no declared limit, confirmed via
`information_schema.columns` (`character_maximum_length` was `NULL`
for every one of them).

The original Module 21 pass added a `max_length=255` Pydantic bound
to `app.schemas.applicant_create.ApplicantCreateRequest` and believed
that covered every write path into `applicant`, since "every other
applicant-creation path -- including Excel import -- ultimately
funnels through the same `applicant` table that this schema alone
directly guards on the write side." That reasoning was wrong: the
Excel-import path (`app.routers.import_.import_applicants`) never
instantiates `ApplicantCreateRequest` at all -- it builds `Applicant`
ORM rows directly from `app.services.excel_import.ParsedRow`, parsed
straight out of the uploaded spreadsheet, completely bypassing the
Pydantic schema. Confirmed live during this follow-up: a real `.xlsx`
with a genuine 5,000-character `Full Name` cell, uploaded through the
real `POST /import/applicants`, was accepted with `created_count: 3,
rejected_count: 0` and landed in the database in full.

That import path is now fixed independently, at parse time
(`app.services.excel_import.parse_workbook` now rejects an oversized
field the same way it already rejects a missing `full_name`/`email`
-- a per-row rejection with a real reason in `error_detail`, counted
under `rejected_count`, not a whole-file failure). This migration adds
the matching database-level `CHECK` constraint as the defense-in-depth
backstop, the same "an application-layer check alone is one omitted
call path away from being wrong" reasoning this project already
applies to `ck_payment_claim_distinct_submitter_confirmer` (migration
0002) and `ck_payment_claim_amount_positive` (migration
0013_positive_amount) -- reused here for the third time, not
reinvented. A hypothetical future write path that bypasses both the
manual-entry schema and the import parser (a raw `INSERT`, a
different endpoint, a data-migration script) is still stopped by the
database itself.

**Verified no existing row violates the constraint before adding it**
(the same "restore the corrupted row first" precedent
`0013_positive_amount` already established for the negative-amount
fix): the one row that would have violated it -- the live test row
created during this follow-up's own reproduction of the defect --
was deleted first; `SELECT ... WHERE length(full_name) > 255 OR ...`
confirmed zero violating rows immediately before this migration ran.

`255`, matching `app.core.field_limits.MAX_FIELD_LENGTH`, the single
shared constant both the Pydantic schema and the import parser now
read from -- not a second, independently-chosen number that could
drift from the application-layer bound over time.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_applicant_field_length"
down_revision: str | None = "0013_positive_amount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEXT_COLUMNS = ("full_name", "email", "phone", "program", "intake_cycle")
_MAX_LENGTH = 255


def upgrade() -> None:
    for column in _TEXT_COLUMNS:
        op.execute(
            f"ALTER TABLE applicant "
            f"ADD CONSTRAINT ck_applicant_{column}_length "
            f"CHECK (length({column}) <= {_MAX_LENGTH})"
        )


def downgrade() -> None:
    for column in _TEXT_COLUMNS:
        op.execute(
            f"ALTER TABLE applicant DROP CONSTRAINT IF EXISTS ck_applicant_{column}_length"
        )
