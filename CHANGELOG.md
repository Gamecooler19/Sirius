# Changelog

Sirius was built module by module, each scoped narrowly and verified against
the real running stack before the next module began (see `CONTRIBUTING.md`
for the process, `reports/` for each module's full report). This changelog
summarizes what each module and its follow-up verification rounds actually
delivered, in order. The project's working name during Modules 01–10 was
"UnivAdmissions"; it was renamed to Sirius in Module 11.

## Module 01 — Foundation

Scaffolded the Docker Compose stack (FastAPI, SQLAlchemy 2.x async,
PostgreSQL 17, PgBouncer transaction pooling, Alembic, Valkey, RustFS), the
core schema and its first five migrations, PostgreSQL row-level security as
defense-in-depth on top of application-level RBAC (ADR-02, ADR-03), ADR-01's
PgBouncer transaction-pooling discipline (`SET LOCAL`, `NULLIF`-wrapped GUC
reads, disabled prepared-statement caching), ADR-07 trigger-based audit
logging, the six seeded roles, a FastAPI RBAC dependency, and session-based
authentication with mandatory TOTP for `SUPER_ADMIN`/`FINANCE_STAFF`/
`FINANCE_MANAGER`. Excel import, status-transition endpoints, and the
payment workflow itself were explicitly deferred to later modules, with
their tables already in place.

Live verification against the real stack caught two real defects: migrations
initially ran as the Postgres bootstrap superuser rather than the intended
`sirius` (then `univadmissions`) application role, which would have silently
defeated every row-level security policy despite the code looking correct;
and `audit_log`'s original RLS policy blocked its own `write_audit()`
trigger's inserts, requiring a split into separate `SELECT`/`INSERT`
policies.

## Module 02 — Status transitions and Excel import

Fixed a naming drift in the `ApplicationStatus` enum (migration
`0006_status_enum_rename`, a genuine semantic remap, not a positional one),
then built a status-transition endpoint enforcing an explicit transition
table and an Excel-import endpoint reconciling uploaded rows against the
existing `applicant` table. Payment-claim submit/confirm was deferred to
Module 03.

**Follow-up verification** closed two gaps in the original verification:
confirmed the migration's old-to-new status remap was genuinely semantic
(multiple old values correctly collapsing to one new value where the old
vocabulary was finer-grained), and verified additional edge-case behavior
against the live stack. Both checks confirmed the existing design; neither
surfaced a new defect.

## Module 03 — Payment workflow

Built the payment-claim submit/confirm/reject workflow: three endpoints
(`POST /finance/payment-claims`, `.../confirm`, `.../reject`) with real
maker-checker enforcement (a submitter cannot resolve their own claim) and a
`total_paid` rollup owned entirely by a database trigger fired on confirm,
never by application code. Migration `0009_payment_claim_workflow` added
`payment_claim.payment_mode`/`reference_number` and discovered that
`finance_record` had no `UPDATE` RLS policy at all — with `FORCE ROW LEVEL
SECURITY` in effect, no role, including `SUPER_ADMIN`, could update a
`finance_record` row, confirmed live before writing the rollup trigger.

## Module 04 — Read endpoints

Added read/list access for applicants (list, detail, status-history, finance
summary), a standalone payment-claims list, and an import-batches list — no
new RLS policy, no new RBAC role, every endpoint a plain `SELECT` through
the existing RLS-scoped session established by Modules 01–03.

**Follow-up verification** closed two gaps: confirmed the applicant-list
filters genuinely combine with `AND` rather than one filter silently
overriding another (verified with a real three-filter case chosen from the
seeded dataset specifically because it excluded a row the first two filters
alone did not), and a second gap in role-gate precision. Both confirmed the
existing design.

## Module 05 — Finance reconciliation

Built `GET /finance/reconciliation`: totals grouped by `intake_cycle`,
derived `outstanding` (fee due minus paid), payment-claim counts/amounts by
status per cycle, and a top-level cross-cycle `totals` object — SQL-level
aggregation throughout, no row-level Python summation.

**Follow-up verification** closed a real gap: the original verification
never exercised a `finance_record` with zero `payment_claim` rows against
it, which the reconciliation query's inner join (rooted at `payment_claim`)
would have silently excluded from its own count. Verified live using
already-seeded data; confirmed the existing two-query design (one query for
finance totals, a separate one for claim counts) already handled this
correctly.

## Module 06 — Frontend foundation

Scaffolded `frontend/`: Vite + React 19 + TypeScript, Mantine, Tailwind
(Preflight disabled), TanStack Query v5, Phosphor Icons — wired to the real
backend with `credentials: "include"`, no bearer token, no dev-server CORS
proxy. Built the full login flow end to end against real `/auth/*`
endpoints: email/password → branch on `totp_required`/
`totp_enrollment_required` → a real QR code and ten backup codes for
first-time enrollment, a six-digit verify step for already-enrolled users,
plain success otherwise. Added `useMe()`, an authenticated app shell with
role-gated navigation, and route guarding on 401.

Live verification (a real Firefox session against the real dev server and
API) caught that Vite's default `server.host` resolves to `localhost` only,
not `127.0.0.1`, which initially broke the CORS origin match — fixed by
aligning the dev server's actual bound origin with `CORS_ORIGINS`.

## Module 07 — Applicant list and detail UI

Built the applicant list (paginated, filterable by `current_status`/
`program`/`intake_cycle`, matching Module 04's filter set exactly) and a
detail drawer with status-history timeline and a status-transition control
copying the server's own transition table for UX purposes only (not
enforcement).

**Follow-up verification** closed three gaps: a real three-filter
combination genuinely narrowing results (found by walking the full seeded
dataset first to identify a case where the third filter actually excluded a
row the first two did not), plus two further edge cases. All three confirmed
the existing design.

## Module 08 — Excel import UI

Built the import upload page (`.xlsx`-restricted picker, real breakdown
render of `created_count`/`updated_count`/`flagged_count`/`rejected_count`,
visible `deduplicated: true` handling, real 422 error surfacing) and the
import-batch history list, reusing Module 07's table/pagination pattern.
RBAC asymmetry: upload restricted to `SUPER_ADMIN`/`ADMISSIONS_MANAGER`;
history additionally visible to `AUDITOR`.

## Module 09 — Payment-claim UI

Built the Finance review queue and a per-applicant finance section embedded
in Module 07's detail drawer, wired to the real payment-claim endpoints. The
frontend reflects a genuine maker-checker asymmetry sharper than Module 08's:
`FINANCE_STAFF` may submit a claim but can never resolve *any* claim,
including their own — the review queue renders no Actions column at all for
a role outside the resolve set, not a column of disabled buttons.

**Follow-up verification** closed two gaps: confirmed the status filter
genuinely narrows the queue server-side (independently counted a status in
the database first, then confirmed the filtered UI result matched exactly),
and a second gap around stale-queue behavior after a resolve action. Both
confirmed the existing design. Temporary TOTP-code helper scripts used
during verification were deleted from both the container and host before
committing.

## Module 10 — Reconciliation dashboard

Built the reconciliation dashboard at `/finance/reconciliation`: summary
cards for the top-level `totals` object plus a per-cycle breakdown table,
gated on `RECONCILIATION_ROLES`. No pagination or filters, matching the
backend endpoint's own shape. Verified a zero-count status renders as a real
`0`, never omitted.

## Module 11 — Reset, rebrand, and repository setup

Brought the stack down with volumes removed for a full local data reset,
regenerated every secret in `deploy/.env` from scratch (database password,
session/TOTP encryption keys, RustFS keys — nothing reused from before),
and brought the stack back up clean. Confirmed via `psql` that all six roles
exist and every other table is empty. Seeded one working login per role with
simple, memorable local-demo passwords, and completed real TOTP enrollment
through the actual `/auth/totp/enroll/start` + `/auth/totp/enroll/confirm`
endpoints for the three mandatory-TOTP roles, verified end to end with a
fresh login and a live-computed TOTP code reaching a protected route.

Renamed the project's user-facing and documentation-facing identity from
"UnivAdmissions" to Sirius everywhere it appeared — page title, README,
`package.json`/`pyproject.toml` name fields, Docker Compose project name,
in-app text, session cookie name, TOTP issuer name, docstrings — while
leaving the filesystem directory path untouched per explicit instruction.
Added the real Forgejo git remote and pushed the complete existing commit
history for the first time. Added `LICENSE`, this `CHANGELOG.md`, a
rewritten `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and
`SECURITY.md` at the repository root.
