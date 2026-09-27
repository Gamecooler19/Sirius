# Module 19: manual single-applicant entry

## Scope

Before this module, an `Applicant` row could only ever be created by
the Excel-import endpoint (`app.routers.import_.import_applicants`) --
a real gap for the ordinary, ongoing case of a counselor taking a
walk-in visitor or a phone inquiry and needing to record that person
as an applicant right now, not batched into tomorrow's spreadsheet.
This module adds `POST /applicants`, the single-row analogue of the
same creation path, deliberately reusing import's own
normalization/matching logic rather than duplicating it, plus a
`GET /applicants/counselors` lookup and a real `ApplicantsPage` "New
applicant" form.

## Backend

### `POST /applicants` (`api/app/routers/applicant_create.py`, new)

**RBAC: `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`ADMISSIONS_COUNSELOR`** --
deliberately the same three roles `app.routers.status.
transition_applicant_status` already owns, wider than import's own
`SUPER_ADMIN`/`ADMISSIONS_MANAGER`-only set. A counselor handling a
walk-in or a phone call is a real, ordinary case this workflow should
support directly; import's own narrower set is about a different risk
(bulk-loading someone else's whole spreadsheet), not one that applies
to a single applicant a counselor is entering about a person standing
in front of them.

### Design decision 1 -- `assigned_counselor_id`, role-dependent

- `ADMISSIONS_COUNSELOR`: the only applicant this role's own RLS
  policy (`applicant.role_visibility`) will ever let them see again
  is one where `assigned_counselor_id` is their own id -- creating a
  row with any other value or `NULL` would produce an applicant this
  same counselor could never see or act on again the moment the
  transaction commits (RLS is fail-closed). So: omitted -> auto-
  assigned to the caller; sent equal to their own id -> same result;
  sent as any *other* counselor's id -> real 422 before any write
  ("an ADMISSIONS_COUNSELOR may only assign a new applicant to
  themselves").
- `SUPER_ADMIN`/`ADMISSIONS_MANAGER`: neither role's own RLS
  visibility depends on this field, so no structural reason to force
  an assignment. Omitted -> created unassigned (`NULL`, "a normal,
  expected state before a counselor picks up a new inquiry," per
  `Applicant`'s own model docstring); sent -> validated to be a real,
  active `ADMISSIONS_COUNSELOR` account (422 otherwise, distinct
  message for "not a counselor" vs. "deactivated account").

### Design decision 2 -- initial status is `APPLIED`, not `IMPORTED`

`ApplicationStatus`'s own docstring and `ALLOWED_TRANSITIONS`'s own
module docstring both describe `IMPORTED` as specifically "a raw row,
unreviewed" -- the status a spreadsheet row starts at *before* anyone
has looked at it or spoken to the applicant. That does not describe a
row a staff member is entering by hand, right now, in the same motion
as an actual conversation with the applicant -- by construction it has
already been reviewed. Starting at `APPLIED` instead -- the status
`ALLOWED_TRANSITIONS` already treats as the first "real pipeline
position" reachable from `IMPORTED` -- correctly skips a state that
only ever meant "came from an unreviewed Excel row," without inventing
a new status value or touching the transition table: `APPLIED` already
exists, and its only current source (`IMPORTED -> APPLIED`) is
unaffected. A real `ApplicationStatusEvent` is written at creation
time too (`from_status=None`, `to_status=APPLIED`, `changed_by=`the
creating user, a real note) -- the same "record the transition"
discipline `transition_applicant_status` applies to every later move,
applied here at creation so the status history starts with a real,
attributed event rather than an applicant that simply appears already
at `APPLIED` with no explanation.

### `import_batch_id` -- confirmed nullable, no migration needed

Checked directly against the live schema (`\d applicant` on the real
running Postgres instance) before writing any code: the column has
always been nullable, no `NOT NULL` constraint. `Applicant`'s own
original model docstring had already anticipated this exact case
("nullable: a future manually-created applicant, if that path is ever
added, would have no batch"). This module is that anticipated case,
arriving -- confirmed true, not assumed, and genuinely needed zero
schema change.

### Duplicate detection -- reused, not reimplemented, with a real gap caught and fixed

`normalize_phone`/`normalize_email` are imported verbatim from
`app.services.excel_import` -- the identical normalization import's
own matching already uses. Phone is checked before email, mirroring
import's own precedence. Unlike import (which treats a match as "same
person, update the record"), a manual creation that collides is
rejected outright with a real `409`, naming the conflicting
applicant's real id (`applicant_id=<uuid>`) -- a counselor/manager
entering a new row is not trying to update an existing applicant.

**A real RLS-interaction gap was caught while implementing this, not
after.** Import's own matching loop never has to think about RLS
scope, because both its callers (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`)
already have full applicant visibility. This endpoint's RBAC is
deliberately wider (`ADMISSIONS_COUNSELOR` included), and that role's
own RLS policy is the narrow, own-rows-only one -- running the
duplicate-detection `SELECT` through the caller's own
`require_role_session`-yielded session would have silently scoped it
to only the applicants that one counselor can already see, letting a
duplicate phone/email belonging to a different counselor's applicant
sail through undetected. Fixed by opening a second, short-lived,
read-only `open_scoped_session(actor_role=SUPER_ADMIN)` purely for the
duplicate scan, distinct from the caller's own transaction that
performs the actual write -- the RLS `WITH CHECK` guarantee on the
insert itself (a counselor cannot insert a row assigned to someone
else) is completely unaffected. This does mean the `409` can reveal
that *some* applicant with a given phone/email exists (and its id) to
a counselor who could not otherwise see that row via `GET
/applicants` -- accepted deliberately, since the alternative (silently
creating a genuine duplicate the rest of the system treats as two
unrelated people) is a strictly worse outcome, and is the exact
integrity guarantee this module was asked to build. Verified live
below (a counselor duplicate-phone attempt against an applicant they
cannot `GET` still gets a real 409 naming it).

### `GET /applicants/counselors` (new, same file)

Minimal `{id, full_name}` list of every active `ADMISSIONS_COUNSELOR`
account, `SUPER_ADMIN`/`ADMISSIONS_MANAGER` only -- the "assign to"
picker's own data source. Deliberately not `UserSummary`/`GET /users`
(both `SUPER_ADMIN`-only end to end and carrying fields, e.g.
`is_active`/`last_login_at`, this narrower lookup has no reason to
expose to an `ADMISSIONS_MANAGER` caller).

### Schema (`api/app/schemas/applicant_create.py`, new)

`ApplicantCreateRequest`: `full_name`, `email` (`EmailStr`), `phone`
(optional), `program`, `intake_cycle`, `assigned_counselor_id`
(optional). No `current_status` or `import_batch_id` field -- the
endpoint decides both itself, never client-supplied. Response reuses
`app.schemas.reads.ApplicantDetail` verbatim (the same shape `GET
/applicants/{id}` already returns).

### Wiring

`applicant_create.router` included in `api/app/main.py`, placed
alongside `status.router` (both own applicant-workflow write paths for
the same three roles).

## Frontend

### `frontend/src/api/types.ts`

`ApplicantCreateRequest` (mirrors the backend schema exactly) and
`CounselorOption` (mirrors `_CounselorOption`).

### `frontend/src/applicants/useApplicants.ts`

- `useCreateApplicant()`: `POST /applicants`, invalidates
  `applicantsKeys.all` on success -- the exact same query key
  `useTransitionApplicantStatus` already invalidates, so a newly
  created applicant appears in the list (and the Home dashboard's
  status-breakdown widget) immediately, no manual reload.
- `useAssignableCounselors(enabled)`: `GET /applicants/counselors`,
  `enabled` lets an `ADMISSIONS_COUNSELOR` session skip the fetch
  entirely (that role has no use for it and would otherwise draw a
  real, expected 403 from the backend's own role gate).

### `frontend/src/applicants/ApplicantsPage.tsx`

New "New applicant" button next to the page title, gated on
`hasRole(me.role_code, APPLICANTS_ROLES)` -- the same role set the nav
link and status-transition workflow already use, matching
`app.routers.applicant_create`'s own `_CREATE_ROLES`. Opens a Mantine
`Modal` containing `NewApplicantForm`:

- Full name / Email / Phone (optional) / Program / Intake cycle
  fields.
- **"Assign to counselor" `Select` only renders for `SUPER_ADMIN`/
  `ADMISSIONS_MANAGER`** (`canAssignOthers`, backed by
  `useAssignableCounselors`) -- an `ADMISSIONS_COUNSELOR` session sees
  a plain "This applicant will be assigned to you automatically" note
  instead, since the backend always auto-assigns that role to
  themselves regardless of what the form could send.
- On failure, the backend's own real rejection text surfaces verbatim
  in an inline `Alert` (the 409's conflicting-applicant-id message,
  the 422 messages) -- not a rewritten generic error, the same
  discipline every other form in this codebase (`CreateUserForm`,
  the TOTP self-reset form) already follows.
- On success: form resets, modal closes, `useCreateApplicant`'s own
  invalidation refreshes the list live.

## Live verification (real running Docker stack, real DB, real browser UI)

All of the following used the actual running containers
(`sirius-api-1` rebuilt with this module's code, `sirius-frontend-1`
hot-reloading the bind-mounted source, `sirius-postgres-1`) -- curl for
backend-only checks, a real Firefox tab driven end to end for the UI
check, direct `psql` for state confirmation. No mocks.

### Confirming `import_batch_id`'s own nullability, live, before writing code

`\d applicant` against the real running Postgres instance: no `NOT
NULL` on `import_batch_id`. Confirmed true, not assumed.

### `SUPER_ADMIN`/`ADMISSIONS_MANAGER` test-account passwords

`admissionsmanager@sirius.app` already had a known working password
from Module 18's own follow-up verification earlier in this session
(`AdmissionsManager123!`). `newcounselor@sirius.app`'s original
password was unknown going in (never previously set by this session) --
established a real, known password (`NewCounselorM19!`) through the
actual `POST /auth/forgot-password` -> real Mailpit email -> real
`POST /auth/reset-password` flow, the same real redemption path every
prior module's own account-setup steps have used, not a direct
database write.

### 1. Counselor creates an applicant -> auto-assigned, RLS-scoped correctly (curl)

Logged in as `newcounselor@sirius.app`
(`86dbe031-9ed0-411d-939e-7538df73965f`). `POST /applicants` with no
`assigned_counselor_id` -> real `201`, `assigned_counselor_id` in the
response genuinely equals the caller's own id, `current_status:
APPLIED`, `import_batch_id: null`.

- `GET /applicants/{id}` as the same counselor -> `200`, visible.
- `GET /applicants/{id}` as a *different* counselor
  (`admissionscounselor@sirius.app`, fully TOTP-verified via a real
  live-generated code) -> real `404` ("applicant not found") -- RLS's
  own fail-closed behavior, confirmed live, not merely trusted from
  reading the policy SQL.

### 2. Manager creates an applicant explicitly assigned to a different counselor (curl)

Logged in as `admissionsmanager@sirius.app`. `POST /applicants` with
`assigned_counselor_id` set to `admissionscounselor@sirius.app`'s real
id -> real `201`, `assigned_counselor_id` in the response matches
exactly what was requested.

- `GET /applicants/{id}` as `admissionscounselor@sirius.app` (the
  assigned counselor) -> real `200`, full detail visible.
- `GET /applicants/{id}` as `newcounselor@sirius.app` (a third,
  unrelated counselor) -> real `404` -- correctly invisible.

### 3. Manager creates an unassigned applicant (curl)

`POST /applicants` with no `assigned_counselor_id` as
`admissionsmanager@sirius.app` -> real `201`,
`assigned_counselor_id: null` in the response -- confirming the
optional-for-manager/admin half of the design decision, not only the
counselor-forced half.

### 4. Genuine duplicate-phone rejection, including across an RLS boundary (curl)

`newcounselor@sirius.app` attempted to create a new applicant using
the same (differently-formatted: `999-888-7772` vs. the stored
`9998887772`) phone number as the applicant from check 2 above -- an
applicant this same counselor cannot even `GET` (confirmed `404` for
them in check 2). Result: real `409`,
`{"detail": "an applicant with this phone already exists
(applicant_id=31386014-c9ee-4169-bd04-ad37957b9246)"}` -- the exact
real conflicting id, and proof the duplicate-detection fix (the
dedicated full-visibility scope) genuinely works across the RLS
boundary it was built to close, not merely in the same-visibility
case. `normalize_phone` also confirmed live to correctly treat
`999-888-7772` and `9998887772` as the same value.

### 5. Counselor attempting to assign a walk-in to someone else (curl)

`newcounselor@sirius.app` sent `assigned_counselor_id` equal to a
*different* counselor's real id -> real `422`, "an ADMISSIONS_COUNSELOR
may only assign a new applicant to themselves" -- the guard fires
correctly, not merely present in the code.

### 6. Manager sending an invalid `assigned_counselor_id` (curl)

A random UUID (`00000000-0000-0000-0000-000000000000`) as
`assigned_counselor_id` from `admissionsmanager@sirius.app` -> real
`422`, "assigned_counselor_id must be an existing ADMISSIONS_COUNSELOR
account."

### 7. Initial status and status-history event, confirmed live

`GET /applicants/{id}/status-history` for the counselor's own
check-1 applicant -> one real event: `from_status: null, to_status:
"APPLIED", changed_by: <the creating counselor's own id>, note:
"Manually created applicant (walk-in/phone entry)"` -- confirms both
the initial-status decision and the creation-time event-write, live.

### 8. `audit_log` sanity check

Queried directly (as `SUPER_ADMIN`, RLS-permitted reader) after the
sequence above: three real `INSERT` rows on `applicant`, `actor_id`
correctly matching each creating user (two by the counselor's own id,
one by the manager's) -- the existing `write_audit()` trigger fires
for this module's new write path with zero code change required, the
same "no special-casing needed" result every prior module's own audit
check has found.

### 9. Real browser UI, end to end (not curl)

Logged in as `newcounselor@sirius.app` through the actual login form
(real Firefox tab, `browser` tool). Navigated to `/applicants` via the
real nav link. Confirmed the real `Applied: 1` count on the Home
dashboard already reflected the counselor's own earlier curl-created
applicant (RLS-scoped correctly, live). Clicked the real "New
applicant" button -> modal opened; confirmed by reading the rendered
modal's own text that **no "Assign to counselor" field is present**
for this role, only the "This applicant will be assigned to you
automatically" note -- the role-conditional rendering works as
designed, confirmed by direct inspection of the actual DOM, not
inferred from the component code. Filled Full name/Email/Phone/
Program/Intake cycle through real form inputs and submitted via the
real "Create applicant" button. Result: the modal closed (Mantine's
own fade-out transition, confirmed via `opacity: 0` on the dialog
element post-submit) and **the new applicant ("Browser UI Walkin")
appeared in the applicants table immediately**, without any manual
reload -- `useCreateApplicant`'s own `applicantsKeys.all` invalidation
confirmed working end to end through the real UI, not merely at the
hook level. Cross-checked via a direct `GET /applicants` call
afterward: the browser-created row was genuinely persisted,
`assigned_counselor_id` correctly equal to the logged-in counselor's
own id.

(One tooling note, not an app defect: Firefox's own "Save login"
password-manager popup rendered visually on top of the modal in a
screenshot taken mid-flow, making the modal appear hidden in that one
screenshot -- confirmed via direct DOM inspection (`document.
querySelector('[role="dialog"]')`) that the real Mantine modal was
open and correctly populated the entire time; the browser's own
autofill-prompt overlay was a z-index visual artifact of the
screenshot, not a rendering bug in this module's own code. The same
class of tooling quirk Module 17/18 already documented for this
project's own browser-automation checks, not a new one.)

## Follow-up verification

Two gaps identified after the module's own original verification pass
-- both closed against the real running stack, not inferred from
reading the code a second time.

### 1. `assigned_counselor_id`'s two distinct rejection messages, both confirmed live and genuinely distinct

The module's own design-decision section claims a manager/admin caller
sending an invalid `assigned_counselor_id` gets a real, specific
rejection -- but the original live verification only ever exercised a
*nonexistent* id (`00000000-0000-0000-0000-000000000000`), not a real
account of the wrong role or a real, existing-but-deactivated
counselor. Both were missing live proof.

**Wrong role, real existing account.** Logged in as
`admissionsmanager@sirius.app`, sent `assigned_counselor_id` equal to
`auditor@sirius.app`'s real id (`1aadd2f4-86b1-4511-9564-9559b3d118d8`,
a genuine `AUDITOR` account, not a counselor at all) -> real `422`,

```
{"detail": "assigned_counselor_id must be an existing ADMISSIONS_COUNSELOR account"}
```

**Existing but deactivated `ADMISSIONS_COUNSELOR`.** No deactivated
counselor account existed in the live database at the time of this
check, so one was created for real: logged in as `superadmin@sirius.app`
(real password + real live-generated TOTP code), called the real
`PATCH /users/{id}` to set `newcounselor@sirius.app`'s
`is_active=false` -- confirmed `200`, `is_active: false` in the
response. With that account genuinely deactivated, sent
`assigned_counselor_id` equal to its id from the manager session ->
real `422`, a **distinct** message:

```
{"detail": "assigned_counselor_id refers to a deactivated account"}
```

**Result: the code genuinely produces two distinct strings, exactly as
the design-decision section promises** -- "not a real counselor at
all" and "a real counselor, but deactivated" are not folded into one
generic message; the report's own design-decision section already
matched what the code does, and this follow-up is what supplies the
live proof that was previously missing rather than a correction.
`newcounselor@sirius.app` was reactivated immediately afterward via a
second real `PATCH` (`is_active=true`, confirmed `200`) and its
`is_active` state was independently re-confirmed via direct `psql`
after cleanup -- no lasting side effect on this shared test account.

### 2. Email-fallback duplicate detection, no phone, across the same RLS boundary the phone-path proof already covered

The module's own original verification proved phone-based duplicate
detection catches a collision even across an RLS visibility boundary
(check 4 in the original report), but never exercised the
*email*-fallback path (`normalized_phone is None` -> falls through to
the email check) at all, with or without an RLS boundary.

**Seed applicant.** Created as `admissionsmanager@sirius.app`:
`full_name="Email Fallback Seed"`, `email="email.fallback.seed@example.com"`,
`phone="9998887799"`, left unassigned -> real `201`,
id `65b8593e-7f28-40f5-b24a-bd71b31c3ed1`.

**Collision attempt, no phone, email only (different case, to also
prove `normalize_email`'s own lowercasing).** Logged in as
`newcounselor@sirius.app` (a counselor with no assignment to, and
therefore no RLS visibility into, the unassigned seed applicant above
-- confirmed separately below). Sent `full_name="Email Duplicate
Attempt"`, `email="Email.Fallback.Seed@example.com"` (mixed case),
no `phone` field at all -> real `409`:

```
{"detail": "an applicant with this email already exists (applicant_id=65b8593e-7f28-40f5-b24a-bd71b31c3ed1)"}
```

The real conflicting id matches the seed applicant exactly, and the
case-insensitive match confirms `normalize_email`'s lowercasing is
genuinely wired into this path, not only the phone path.

**Confirmed this crosses the same RLS boundary the phone-path proof
already established.** `GET /applicants/65b8593e-...` as
`newcounselor@sirius.app` -> real `404` ("applicant not found") --
this counselor genuinely cannot see the seed applicant through the
ordinary read endpoint (it is unassigned, and this role's own RLS
policy only grants visibility into rows assigned to itself), yet the
email-fallback duplicate check still found and named it. This is the
same dedicated-full-visibility-scope fix documented in the module's
own "Duplicate detection" section doing its job on the email path, not
only the phone path it was originally proven against.

**Cleanup.** The seed applicant and its status-history event were
deleted directly from the database afterward; confirmed via a
follow-up `SELECT` that no rows from either check remain.

## Cleanup performed before treating this module as done

- All 4 test applicants created during verification (`Walkin Test
  One`, `Manager Assigned Walkin`, `Unassigned Walkin`, `Browser UI
  Walkin`) deleted directly from the database afterward, along with
  their `application_status_event` rows -- confirmed via a follow-up
  `SELECT` that zero test-data rows remain. Confirmed via `audit_log`
  that all 4 deletes were themselves captured by `write_audit()`,
  consistent with this project's existing audit-trail discipline.
- `newcounselor@sirius.app`'s password intentionally left at its new,
  real, working value (`NewCounselorM19!`) rather than reverted --
  the original was never known to this session (an unknown legacy
  value, not one this session changed away from a known original),
  matching Module 15/18's own precedent for a test account whose
  prior credential was never available to revert to.
- All temporary curl cookie jars and the one-off TOTP-code-generation
  script copied into the `api` container were deleted.

## Final checks

- `tsc --noEmit` (run inside the real `sirius-frontend-1` container):
  clean.
- `git status`: only this module's own files touched (`api/app/main.py`,
  `api/app/routers/applicant_create.py` (new),
  `api/app/schemas/applicant_create.py` (new),
  `frontend/src/api/types.ts`,
  `frontend/src/applicants/ApplicantsPage.tsx`,
  `frontend/src/applicants/useApplicants.ts`); no stray temp files.
- No real defects surfaced by live verification beyond the one
  RLS-scoping gap in duplicate detection, which was caught and fixed
  *during* implementation (documented above) rather than left latent
  for verification to discover -- every live check in this report
  passed on its first genuine attempt.
