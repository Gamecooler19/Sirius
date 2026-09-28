"""Shared free-text field-length constant for `applicant`'s own text
columns (Module 21 follow-up).

**Why this exists as its own tiny module, not just repeated as `255`
in each of the three places that need it.** `full_name`/`email`/
`phone`/`program`/`intake_cycle` all share the identical length bound
across three genuinely independent write paths into the same
`applicant` table -- `app.schemas.applicant_create.
ApplicantCreateRequest` (manual entry, `POST /applicants`),
`app.services.excel_import.parse_workbook` (bulk import,
`POST /import/applicants`), and the database's own `CHECK` constraints
on the `applicant` table itself (migration `0014_applicant_field_length`,
the defense-in-depth backstop for both application-layer paths, and
for any future or direct-SQL write neither of them ever sees). A
single, named constant makes "why 255, specifically" answerable in one
place and makes a future change to the bound (if one is ever needed)
a one-line edit instead of three call sites that must be kept in sync
by hand.
"""

MAX_FIELD_LENGTH = 255
