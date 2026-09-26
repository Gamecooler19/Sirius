# Module 07: Applicant List and Detail UI — completion report

## Scope

Build the applicant list and detail view in `frontend/`, wired to the real
`GET /applicants`, `GET /applicants/{id}`, `GET /applicants/{id}/status-history`,
and `POST /applicants/{id}/status` endpoints — no mocked data. The list
page replaces `ApplicantsPage`'s Module 06 placeholder with a Mantine
table driven by a TanStack Query hook, paginated using the API's own
`limit`/`offset` shape with visible page controls, filterable by
`current_status`/`program`/`intake_cycle` matching Module 04's actual
filter set exactly. Clicking a row opens a detail drawer showing the
applicant's own fields plus its status-history timeline in chronological
order. The status-transition control copies the exact transition table
already enforced server-side (`app/services/status_transitions.py`) into
a frontend constant the same way Module 06 copied
`APPLICANTS_ROLES`/`FINANCE_ROLES`, using it only to show valid next-states
as selectable and disable the rest — UX convenience, not enforcement. The
transition control is gated on `APPLICANTS_ROLES`. A successful transition
invalidates the list/detail/status-history query caches so the UI reflects
the new state without a manual reload.

## What was built

### Types (`src/api/types.ts` additions)

`ApplicationStatus` (the eight-value enum, mirroring
`app.models.enums.ApplicationStatus` exactly), `ApplicantSummary`,
`ApplicantListResponse`, `ApplicantDetail`, `StatusHistoryEvent`,
`StatusHistoryResponse`, `StatusTransitionRequest`,
`StatusTransitionResponse` — every field copied one-to-one from
`api/app/schemas/reads.py` and `api/app/schemas/status.py`, not a
reshaped superset.

### Transition table (`src/applicants/statusTransitions.ts`)

`ALLOWED_TRANSITIONS`, a plain object copied field-for-field from
`api/app/services/status_transitions.py::ALLOWED_TRANSITIONS` (same
seven source states, same destination sets, same three terminal states
with no key at all). `allowedNextStatuses(from)` mirrors
`is_transition_allowed`'s own lookup shape. `ALL_STATUSES` is the full
eight-value list in pipeline order, used both for the status *filter*
dropdown and to render every status as an option in the transition
`Select` (valid ones enabled, invalid ones `disabled: true`) rather than
omitting invalid destinations outright — the user can see the whole
pipeline, just not act on the disallowed parts of it. The module's own
docstring states explicitly, following the same pattern as Module 06's
`roles.ts`: this table decides what the UI *offers*, not what the backend
*permits* — `is_transition_allowed` on the server is the actual gate.

### Query hooks (`src/applicants/useApplicants.ts`)

- `useApplicantsList(params)` — `GET /applicants?limit=&offset=&current_status=&program=&intake_cycle=`,
  building the query string from exactly those five params (no invented
  filter). `placeholderData: (prev) => prev` keeps the previous page's
  rows visible during a page/filter transition rather than flashing to an
  empty table.
- `useApplicantDetail(id)` / `useApplicantStatusHistory(id)` — `GET /applicants/{id}`
  and `GET /applicants/{id}/status-history`, both `enabled: id !== null`
  so they only fire once a row is actually selected.
- `useTransitionApplicantStatus(applicantId)` — `POST /applicants/{id}/status`.
  `onSuccess` invalidates the `["applicants"]` query-key root, which
  covers the list, this applicant's detail, and its status-history in one
  call — all three caches the transition could have changed.

### List page (`src/applicants/ApplicantsPage.tsx`)

Replaces Module 06's placeholder at the same `/applicants` route. A
Mantine `Select` (status, all eight values plus "All statuses"), two
`TextInput`s (program, intake cycle) drive the three real filter params;
changing any of them resets to page 1. A Mantine `Table` renders
name/email/program/intake-cycle/status (color-coded `Badge` per status)
for the current page; `PAGE_SIZE = 10`, `offset = (page - 1) * 10`, fed
straight into `useApplicantsList`. A Mantine `Pagination` control plus a
"Showing X-Y of Z" caption both derive from the real `total`/`limit`/`offset`
the backend returned, not a client-side estimate. Clicking a row opens
`ApplicantDetailDrawer` for that applicant's id.

### Detail drawer (`src/applicants/ApplicantDetailDrawer.tsx`)

A Mantine `Drawer` showing the applicant's name/email/phone/program/
intake-cycle/current-status, a status-transition section, and a
status-history `Timeline` in chronological order (the backend's own
`ORDER BY created_at ASC`, rendered as-is). The transition section:

- Hidden behind `hasRole(me.role_code, APPLICANTS_ROLES)` — if the
  session's role isn't in that set, the text "Your role cannot transition
  applicant status" shows instead of any control.
- If the applicant's current status is terminal (no entries in
  `allowedNextStatuses`), shows "X is a terminal status -- no further
  transitions are possible" instead.
- Otherwise, a `Select` listing all eight statuses with only the allowed
  next-states enabled, an optional note `Textarea`, and an "Apply
  transition" button calling `useTransitionApplicantStatus`. Any error
  from that call — whatever `ApiError.message` actually says — renders in
  a red `Alert`; there is no separate generic-message branch that could
  shadow the backend's real text. Success renders a green "Status
  updated." `Alert` and resets the form fields.

## Verification against the live stack

Verified against the real running Docker Compose stack
(`sirius-api-1` on `127.0.0.1:38210`, real Postgres data already
seeded by Modules 01-05's own prior live verification -- 36 real
`applicant` rows) and a real Firefox browser session driving the real
Vite dev server at `http://127.0.0.1:5173` (the same origin binding fixed
in Module 06's Defect 1). No mocked responses, no synthetic fixtures
created for the read paths -- the existing `m3-`/`m4-` seed data from
prior modules' own verification was used as-is.

- **Pagination at a real page boundary.** Logged in as `m4-manager@...`
  (`ADMISSIONS_MANAGER`). Page 1 showed 10 of 36 with pagination controls
  for pages 1-4. Clicking page 4 showed exactly **31-36 of 36** (6 rows,
  the correct partial final page) — confirmed the underlying network call
  was `GET /applicants?limit=10&offset=30`, and the real backend response
  had `total: 36, items.length: 6, limit: 10, offset: 30`.
- **Each filter individually.**
  - `current_status=ADMISSION_TAKEN` alone: 3 of 3 results, all
    `ADMISSION_TAKEN` — matching a direct `SELECT current_status,
    count(*) FROM applicant GROUP BY 1` beforehand.
  - `intake_cycle=Spring2027` alone: 3 of 3 results, all `MBA`/`Spring2027`
    — matching the DB's own `program, intake_cycle` grouping.
  - `program=CS` combined with the status filter above (see next point).
- **Filters in combination.** `current_status=ADMISSION_TAKEN` +
  `program=CS` together narrowed the 3-row status-only result down to
  **2 of 2** (excluding the one `ADMISSION_TAKEN` row that's `MBA`), and
  adding `intake_cycle=Fall2026` on top kept it at 2 of 2 (both matched
  rows already were `Fall2026`) — the frontend passed all three params in
  the same request rather than filtering client-side after a single-param
  fetch.
- **A real end-to-end status transition through the UI.** Opened the
  detail drawer for `M4 Applicant A22` (`APPLIED`, `CS`/`Fall2026`,
  existing history "IMPORTED → APPLIED"). The `Select` correctly enabled
  only `IN_PROCESS`/`REJECTED`/`WITHDRAWN` (confirmed by inspecting the
  live DOM's `data-combobox-disabled` attributes: `IN_PROCESS` = enabled,
  `IMPORTED`/`APPLIED`/`ON_HOLD`/`ADMISSION_OFFERED`/`ADMISSION_TAKEN` =
  disabled). Selected `IN_PROCESS`, entered a note, clicked "Apply
  transition" — the real `POST /applicants/{id}/status` fired, returned
  200, the drawer immediately showed a green "Status updated." alert, the
  "Current status" badge flipped to `IN_PROCESS` in place, and a new
  "APPLIED → IN_PROCESS" entry with the real note and a real timestamp
  appeared at the bottom of the status-history timeline — all without any
  page reload. Closing the drawer and looking at the list (still on the
  same page, no reload) showed the same row's status badge already
  updated to `IN_PROCESS`, confirming the query-cache invalidation
  reached the list, not only the drawer's own local state.
- **An attempted invalid transition surfacing the real 422 text.**
  Reproduced a genuinely stale-client scenario rather than merely
  bypassing the UI's own disabling: opened the drawer for `M4 Applicant
  A18` (`APPLIED`), selected the then-valid `REJECTED` destination in the
  real `Select`, then updated the applicant's `current_status` directly in
  Postgres to `ADMISSION_TAKEN` (simulating another actor's concurrent
  change / a stale tab) without refreshing the drawer. Clicking "Apply
  transition" sent the now-invalid `REJECTED` request against the
  now-`ADMISSION_TAKEN` applicant; the real backend rejected it with 422,
  and the drawer's red `Alert` showed **exactly**
  `"invalid status transition: ADMISSION_TAKEN -> REJECTED"` — the
  backend's own `HTTPException` detail string verbatim, not a generic
  frontend message, and the UI neither crashed nor showed a blank state.
  The applicant was restored to `APPLIED` afterward.
- **ADMISSIONS_COUNSELOR's list scoped to only their own assigned
  applicants.** Logged in as `m4-counselor-b@...` (an `ADMISSIONS_COUNSELOR`
  with exactly 3 applicants assigned per a direct DB check beforehand:
  `assigned_counselor_id = '<m4-counselor-b's id>'` on `M4 Applicant B00/B01/B02`).
  The applicant list showed **exactly 1-3 of 3** — those three rows and no
  others — with no client-side filter applied, confirming the RLS
  `role_visibility` policy Module 04 already verified server-side
  (`ADMISSIONS_COUNSELOR` restricted to `assigned_counselor_id =
  app.actor_id`) genuinely reaches the rendered screen, not merely the API
  response a curl call would see.
- **Transition-control role gating, both directions.** As the counselor
  above (in `APPLICANTS_ROLES`), the transition `Select`/button rendered
  normally. Logged in separately as `frontend-auditor@...` (`AUDITOR`, not
  in `APPLICANTS_ROLES` — the Module 06 test fixture): the Applicants nav
  link itself was correctly absent (per Module 06's own gating), but
  navigating directly to `/applicants` by URL still worked (matching
  `applicants_read`'s own "open to all six roles, RLS narrows rows" design)
  and opening a detail drawer showed "Your role cannot transition
  applicant status" instead of any control. A direct
  `POST /applicants/{id}/status` call as this same AUDITOR session
  confirmed the backend independently rejects with **403
  `"insufficient role for this action"`** — the frontend hiding the
  control is genuinely UX convenience only; removing it would not have
  opened any real access.
- **Build and typecheck.** `npx tsc -b` and `npm run build` both pass with
  zero errors against the final source tree.

## Real defects found during this verification

None. Every behavior above matched the intended design on the first
working attempt once the correct dev origin (`127.0.0.1:5173`, per Module
06's Defect 1 fix) was used. The one interaction worth calling out
explicitly, since it could look like a defect at a glance: Mantine's
`Drawer` leaves its overlay element in the DOM at `opacity: 0` rather than
unmounting it, so a coordinate-based click issued while the drawer is
closed can land on the invisible overlay instead of the element
underneath it (encountered a few times purely as an artifact of this
verification's own click-by-coordinate tooling, never as something a real
user driving the actual UI with a mouse or keyboard would hit) — worked
around during verification by dispatching clicks against the specific DOM
node instead of screen coordinates. Not a defect in the shipped UI itself.

## Explicitly out of scope (per module boundary)

The payment workflow and reconciliation view remain untouched empty
placeholder routes from Module 06. No RBAC logic was duplicated beyond
`ALLOWED_TRANSITIONS`/`APPLICANTS_ROLES`, both copied verbatim from
backend source per this module's own instruction; the backend
(`app.services.status_transitions.is_transition_allowed`,
`app.core.deps.require_role_session`, and RLS) remains the actual
enforcement point for every behavior this module's UI merely reflects.

## Follow-up verification

Three gaps in this module's own original verification, closed against the
same live stack and, for two of the three, data already sitting in it —
no new fixtures created for any of them. All three confirmed the existing
design; none surfaced a real defect, so no code change was needed.

### 1. A real three-filter case where the third filter actually excludes a row

The original report verified two-filter combinations
(`current_status=ADMISSION_TAKEN` + `program=CS`, then + `intake_cycle=Fall2026`
on top) but that third addition happened to exclude nothing new — both
matched rows were already `Fall2026`, so the check never actually proved a
third filter narrows anything beyond what the first two already had.

Walked the full 36-row seeded dataset first (`psql`) to find a genuine
combination where adding a third filter excludes at least one row the
first two alone would include, rather than constructing one via a status
transition: `current_status=IMPORTED` + `intake_cycle=Fall2026` matches
**20** rows spanning both `CS` (9) and `ECE` (11); adding `program=CS` on
top narrows this to exactly **9**, excluding all 11 `ECE` rows the
two-filter query alone would have returned. This combination already
existed in the live seed data — no new fixture, no status transition
needed.

Reproduced through the real UI (not curl): as `m4-manager@...`, applied
`intake_cycle=Fall2026` then `current_status=IMPORTED` — the real network
request was `GET /applicants?limit=10&offset=0&current_status=IMPORTED&intake_cycle=Fall2026`,
result `"Showing 1-10 of 20"`. Adding `program=CS` produced
`GET /applicants?limit=10&offset=0&current_status=IMPORTED&program=CS&intake_cycle=Fall2026`,
result **"Showing 1-9 of 9"** — every one of the 9 visible rows confirmed
`CS`/`Fall2026`/`IMPORTED` by direct inspection, with zero `ECE` rows
present. `9 < 20`, and `9` is the exact intersection size computed
independently from the seed data beforehand, not merely "smaller than
before" — confirming the frontend passes all three active params together
in one request and the backend's own `AND`-composed filter list narrows
correctly across three simultaneous constraints, not just two. No code
change needed.

### 2. Filtering from a page other than 1 resets to offset 0, not a stale out-of-range offset

The original report tested pagination and filters independently but never
in the same session in that order — leaving open whether choosing a filter
while sitting on, say, page 3 of the unfiltered list would carry the
existing page/offset state forward into the filtered request (producing a
`GET /applicants?offset=20&...` against a filtered set that might only
have 3 total rows, i.e. a request entirely past the end of the result set)
or correctly reset to page 1/offset 0.

As `m4-manager@...` (36 total, unfiltered), navigated to page 3 (confirmed
via the visible "Showing 21-30 of 36" and the pagination control
highlighting "3"). Instrumented `window.fetch` to capture the exact
outgoing request URL, then applied `intake_cycle=Spring2027` (a filter
whose real total is 3, far short of an offset-20 request). The actual
network call fired was **`GET /applicants?limit=10&offset=0&intake_cycle=Spring2027`**
— `offset=0`, not the stale `offset=20` from page 3 — and the visible
result was "Showing 1-3 of 3" with the pagination control showing page
"1", not "3" or a blank/broken page. This confirms `ApplicantsPage`'s own
`resetToFirstPage()` call (invoked from every filter's `onChange` handler)
does what it's named for, and that the `page` state feeding
`useApplicantsList`'s `offset` calculation is the same state the
`Pagination` control renders from — no separate, driftable copy of
"current page" existed in the code that could get the reset while the
other didn't. No code change needed.

### 3. Terminal-status applicant shows the correct message, not an empty or broken control

The original report exercised the terminal-status branch only indirectly
(by deriving from `allowedNextStatuses` returning an empty array in code
review), never by actually opening the drawer for a real applicant
already sitting at a terminal status.

Opened the detail drawer for `M3 Finance Test Applicant`
(`ADMISSION_TAKEN`) — Module 03's own leftover applicant, the same one
Module 04's report used to demonstrate the finance-record RLS narrowing
and whose `application_status_event` history is genuinely empty (its
status was set via a direct `psql UPDATE` during Module 03's own setup,
never through the real transition endpoint, exactly as Module 04's report
already documented). The drawer rendered exactly:
`"ADMISSION_TAKEN is a terminal status -- no further transitions are
possible."` — no `Select` control, no disabled empty dropdown, no crash,
and the "Status history" section correctly showed "No status changes
recorded yet." beneath it (the genuine empty-history case, not a loading
spinner stuck open or an error). Confirmed as the logged-in
`ADMISSIONS_MANAGER` — a role that *is* in `APPLICANTS_ROLES` — so this
was specifically the terminal-status branch firing, not the separate
role-gate branch from the original report's own AUDITOR check. No code
change needed.

