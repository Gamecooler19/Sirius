# Module 08: Excel Import UI — completion report

## Scope

Build the Excel import UI in `frontend/`: an upload page wired to the real
`POST /import/applicants` (Module 02) and an import-batches history list
wired to the real `GET /import-batches` (Module 04) — no mocked
responses. `multipart/form-data`, not JSON, so the API client needed a
distinct method passing a raw `FormData` body and letting `fetch` set its
own `Content-Type` boundary header. The upload page: a `.xlsx`-restricted
file picker (UX convenience, matching the backend's own restriction, not
enforcement), a submit button, a loading state, and a real breakdown
render of `created_count`/`updated_count`/`flagged_count`/`rejected_count`
plus `flagged_rows`/`error_detail` as readable tables/lists, not a raw
JSON dump. A `deduplicated: true` response renders visibly differently
from a fresh import. A 422 (missing/renamed column) surfaces the
backend's real error text via the existing `ApiError` path. A successful,
non-deduplicated import invalidates the applicant-list query cache. The
history page lists prior batches (filename, uploader, timestamp, status,
all four counts) using Module 07's own table/pagination pattern. RBAC has
a genuine asymmetry: upload restricted to
`SUPER_ADMIN`/`ADMISSIONS_MANAGER`; history visible to those two plus
`AUDITOR`.

## What was built

### API client (`src/api/client.ts`)

`api.postFormData<T>(path, formData)` — a new method distinct from
`api.post`. The shared `request()` helper now checks
`init?.body instanceof FormData` and skips the `Content-Type:
application/json` header entirely for that case, letting `fetch`/the
browser compute and attach `multipart/form-data; boundary=...` itself
once the body is actually serialized on the wire — the boundary value is
only known at that point, so setting `Content-Type` manually (even to a
look-alike `"multipart/form-data"` string with no boundary) would
silently corrupt the body and the backend would fail to parse any part of
it. JSON bodies via `api.post` are completely unaffected.

### Types (`src/api/types.ts` additions)

`ImportBatchStatus`, `ImportBatchResponse` (mirrors
`api/app/schemas/import_batch.py::ImportBatchResponse` field-for-field,
including `flagged_rows: Record<string, unknown>[] | null` since the
backend itself declares that field as an untyped `list[dict] | None`
JSONB column, built ad hoc per-row in the router — not a schema this
frontend should pretend is narrower than it really is), `ImportBatchSummary`/
`ImportBatchListResponse` (mirrors `api/app/schemas/reads.py` exactly).

### Roles (`src/auth/roles.ts` additions)

`IMPORT_UPLOAD_ROLES` (`SUPER_ADMIN`, `ADMISSIONS_MANAGER` — copied from
`app.routers.import_.import_applicants`'s own `require_role_session` call)
and `IMPORT_HISTORY_ROLES` (`SUPER_ADMIN`, `ADMISSIONS_MANAGER`, `AUDITOR`
— copied from `app.routers.import_batches_read.list_import_batches`'s own
`_LIST_ROLES`). The module docstring states the asymmetry explicitly:
these are two genuinely different sets, not one gate reused for both
pages, matching the real backend split.

### Query hooks (`src/import/useImport.ts`)

- `useImportBatchesList(params)` — `GET /import-batches?limit=&offset=`,
  same `placeholderData` pattern as Module 07's `useApplicantsList` to
  avoid flashing empty during a page change.
- `useImportApplicants()` — builds a real `FormData` (`formData.append("file",
  file)`) and calls `api.postFormData("/import/applicants", formData)`.
  `onSuccess` invalidates the applicants-list query-key root
  (`applicantsKeys.all`, imported from `applicants/useApplicants.ts`) and
  the import-batches query-key root, but **only when `!result.deduplicated`**
  — a dedup short-circuit touches nothing server-side (the backend's own
  docstring: "touches nothing else -- no new import_batch row, no
  applicant reads or writes"), so invalidating any cache for that case
  would be pure overhead with nothing new to actually reflect.

### Upload page (`src/import/ImportUploadPage.tsx`)

Gated on `IMPORT_UPLOAD_ROLES` via `hasRole` — a role outside that set
sees `"Your role cannot run an applicant import."` and no file input, no
button, no disabled control implying near-access. For an allowed role: a
Mantine `FileInput` with `accept=".xlsx"` (client-side UX restriction
only, named as such in the component's own docstring — the backend's own
`file.filename.lower().endswith(".xlsx")` check remains the actual
enforcement), an "Upload" button (`loading` while the mutation is
pending, `disabled` with no file chosen), and a result renderer:

- `deduplicated: true` → a distinct blue "Already imported" `Alert`
  naming the real prior batch id, explicitly stating "No new rows were
  created or updated" — structurally nothing like the success card below,
  not the same layout with zero counts.
- Otherwise → a `Card` with the `COMPLETED`/`FAILED` status badge, the
  four counts as large readable numbers (`created_count`/`updated_count`/
  `flagged_count`/`rejected_count`), a green confirmation that new/updated
  applicants now appear in the list when either count is nonzero, a real
  `Table` of `flagged_rows` (row number, applicant id, old→new email,
  old→new phone, reason — reading each entry's known keys defensively
  since the backend's own type for this field is an untyped dict), and a
  `List` of `error_detail`'s `"; "`-joined rejected-row messages, one
  `List.Item` per rejected row, naming the row number and the missing
  field(s) verbatim from the backend's own text.
- A 422 (thrown as `ApiError` before any `ImportBatchResponse` exists)
  renders in a separate red `Alert` with `error.message` — the backend's
  own text (e.g. `"import rejected: missing expected column(s): Full
  Name"`), not a rewritten frontend message.

### History page (`src/import/ImportHistoryPage.tsx`)

Same `Table` + `Pagination` + "Showing X-Y of Z" shape Module 07's
`ApplicantsPage` already established, driven by `useImportBatchesList`.
Columns: filename, uploaded-at + uploader id, status badge, and all four
outcome counts. No role gate rendered *inside* this component beyond what
the real `GET /import-batches` response itself enforces — visibility is
`IMPORT_HISTORY_ROLES` at the nav-link level (`AppShellLayout`); a role
outside that set who reaches this route by direct URL gets the real
backend's 403 text in an `Alert` (see Defect 1 below for why that error
now surfaces promptly rather than hanging).

### Nav and routing (`AppShellLayout.tsx`, `router.tsx`)

Two new nav entries, each gated independently: "Import applicants" (`/import`)
on `IMPORT_UPLOAD_ROLES`, "Import history" (`/import/history`) on the
wider `IMPORT_HISTORY_ROLES` — so `AUDITOR` sees the history link but not
the upload link, exactly matching the backend's real asymmetry.

## Verification against the live stack

Verified against the real running Docker Compose stack
(`sirius-api-1` on `127.0.0.1:38210`) and a real Firefox browser
session driving the real Vite dev server at `http://127.0.0.1:5173`. Real
`.xlsx` files were built with `openpyxl` the same way Module 02's own
verification built them (exact `COLUMN_MAP` header text: `Full Name`,
`Email`, `Phone`, `Program`, `Intake Cycle`), then served over a small
local CORS-enabled HTTP file server so the real browser could `fetch()`
them into actual `File`/`Blob` objects and dispatch them into the real
`<input type="file">` via a `DataTransfer`, firing React's own
`onChange` handler exactly as an OS file-picker selection would — this
project's own automated `upload` browser-tool action was non-functional
in this environment (returned "uploadFile requires 'path' param" for
every path/selector combination tried), so this `DataTransfer` technique
was the substitute that still drives the **app's own code path** (its own
`FileInput` state, its own `FormData` construction, its own
`api.postFormData` call) end to end — not a synthetic `FormData` built by
a test script bypassing the UI, and not curl.

- **A fresh import whose new applicants actually appear in the applicant
  list without a reload.** Logged in as `m4-manager@...`
  (`ADMISSIONS_MANAGER`). Uploaded a real 2-row `.xlsx`
  (`M8 Fresh Applicant One`/`Two`, both new emails/phones) through the
  real file input and "Upload" button: the app showed
  `Created: 2, Updated: 0, Flagged: 0, Rejected: 0`, `COMPLETED`. A direct
  `psql` check confirmed both rows now exist in `applicant` at
  `IMPORTED`. Without any page reload, client-side navigation to
  `/applicants` and filtering by `program=CS` showed the applicant-list
  total climb from 17 to 19 and both `M8 Fresh Applicant One`/`Two` rows
  directly visible on the list's second page — the query-cache
  invalidation genuinely reached the list.
- **Re-uploading the identical file shows the distinct dedup message.**
  The exact same file bytes, re-fetched and re-dispatched into the file
  input, uploaded again: the app showed a **structurally different** blue
  "Already imported" `Alert` naming the real prior batch id
  (`995add29-4d4f-4423-b2d4-59fd3b297e37`), not the green success card
  with zero counts. A `psql` check confirmed the applicant count for
  those two emails was still exactly 2 — no duplicates created.
- **A renamed-header file surfaces the real 422 text.** A real `.xlsx`
  with `Full Name` renamed to `Applicant Name` in row 1, uploaded through
  the real file input: the app's red `Alert` showed exactly
  `"import rejected: missing expected column(s): Full Name"` — the
  backend's own `HTTPException` detail string verbatim.
- **A file with both good and bad rows shows correct counts and per-row
  error detail.** A real 3-row `.xlsx` (one good new applicant, one row
  missing `Email`, one row missing `Full Name`): the app showed
  `Created: 1, Rejected: 2`, with a "Rejected rows" list showing exactly
  `"row 3: missing required field(s) (email)"` and
  `"row 4: missing required field(s) (full_name)"` — readable per-row
  text naming which row and why, not a raw JSON dump of `error_detail`.
- **A flagged row renders as a real table with old/new values.** A
  fourth real `.xlsx` row reusing `M8 Fresh Applicant One`'s exact phone
  (`9990000001`) with a changed email: the app showed
  `Flagged: 1` and a "Flagged rows" `Table` with the real matched
  applicant id, `m8-fresh-one@test.local → m8-fresh-one-NEWEMAIL@test.local`,
  the unchanged phone shown both sides, and the reason text
  `"matched applicant's email or phone changed"` — a `psql` check
  confirmed the applicant's email genuinely was updated to the new value
  (per the backend's own documented "still updates... does not silently
  overwrite... and call it resolved" design), while still counted as
  flagged, not updated.
- **The resulting batches all appear correctly in the history list.**
  `/import/history` (as the same manager) listed all five batches from
  this session (the two fresh-import attempts, the renamed-header
  failure, the mixed-rows file, the flagged-row file) plus Module 07's
  own prior `m4_import.xlsx` batch, each row showing the correct
  filename, real timestamp, real uploader id, correct status badge
  (`COMPLETED`/`FAILED`), and all four counts matching exactly what each
  upload's own result screen had shown moments earlier.
- **`AUDITOR` reaches the history page and its nav link but has no upload
  path at all.** Logged in as `frontend-auditor@...` (`AUDITOR`, the
  Module 06 test fixture): the nav showed Home/Finance/**Import history**
  — no "Import applicants" link anywhere. Clicking "Import history"
  showed the real batch list (same five rows). Navigating directly to
  `/import` by URL (not nav-linked) showed
  `"Your role cannot run an applicant import."` with no file input, no
  button — not a disabled one. A direct `POST /import/applicants` call as
  this same session confirmed the backend independently rejects with
  **403 `"insufficient role for this action"`** — the frontend's absent
  control is genuinely UX convenience, not the real boundary.
- **`ADMISSIONS_COUNSELOR` cannot reach either page or nav item at all.**
  Logged in as `m4-counselor-a@...`: the nav showed only Home/Applicants
  — neither "Import applicants" nor "Import history" present. Direct URL
  navigation to `/import` showed the same "cannot run an applicant
  import" message. Direct URL navigation to `/import/history` showed the
  real backend's `"insufficient role for this action"` text in a red
  `Alert` (see Defect 1 — this only surfaced correctly after the fix
  below; before it, the page hung with neither a loader nor an error).
  This counselor's own, genuinely-permitted `/applicants` page was
  re-checked immediately afterward and confirmed completely unaffected by
  the fix (`Showing 1-10 of 30`, their own 30 assigned applicants).
- **Build and typecheck.** `npx tsc -b` and `npm run build` both pass with
  zero errors against the final source tree, after removing all temporary
  debug instrumentation added mid-verification.

## Real defect found and fixed during this verification

**Defect 1 — the global TanStack Query retry policy retried 403s (and
every other 4xx), which could leave a query stuck showing neither a
loader nor its own error for several seconds.** `App.tsx`'s
`QueryClient` `retry` function (from Module 06) only special-cased
`status === 401`; every other error, including a `403` that will
**never** succeed on retry (a role rejection is not transient), still
went through up to 2 more attempts with TanStack Query's default
exponential backoff. Caught live: logged in as `ADMISSIONS_COUNSELOR` and
navigated to `/import/history` (a route this role cannot see in its own
nav, reached here only by direct URL as part of this exact verification
step) — the real `GET /import-batches` call correctly returned `403`
immediately, but the page rendered only its `<Title>`, with neither the
`Loader` nor the red error `Alert` ever appearing, for far longer than a
single request round-trip. Root-caused by adding temporary debug
instrumentation to read the query's own internal state directly: `status:
"pending"`, `fetchStatus: "paused"`, `failureCount: 1`,
`failureReason: "ApiError: insufficient role for this action"` — the
query had already failed once with the real 403, correctly recorded it as
the failure reason, and was sitting in a scheduled-retry state rather
than surfacing that failure to the UI at all, because `isError` does not
become `true` until retries are exhausted. **Fix:** changed the retry
predicate to reject retrying *any* 4xx status
(`error.status >= 400 && error.status < 500`), not only 401 — a 403, 404,
or 422 all mean the identical request will fail identically again, so
none of them should ever be retried; only a genuine transient failure
(network error, 5xx) is worth the two extra attempts. Re-verified live
after the fix: the identical counselor-navigates-to-`/import/history`
scenario now shows the real
`"insufficient role for this action"` text in a red `Alert`
**immediately**, and the legitimate-access paths (`AUDITOR`'s own history
page, the manager's upload flow, the counselor's own `/applicants` page)
were all re-confirmed unaffected by the change. This fix lives in
`App.tsx`, shared by every query in the app, not only this module's
own two new hooks — any future page hitting a 403/404/422 benefits from
the same fix, not just Module 08's.

## Explicitly out of scope (per module boundary)

No RBAC logic was duplicated beyond `IMPORT_UPLOAD_ROLES`/
`IMPORT_HISTORY_ROLES`, both copied verbatim from the backend's own
`require_role_session`/`_LIST_ROLES` declarations. The backend
(`app.routers.import_.import_applicants`,
`app.routers.import_batches_read.list_import_batches`) remains the actual
enforcement point for every access decision this module's UI merely
reflects or hides controls for.
