# Module 01: Foundation — completion report

## Scope

Scaffold the foundation for Sirius: Docker Compose stack (FastAPI,
SQLAlchemy 2.x async, PostgreSQL, PgBouncer transaction pooling, Alembic,
Valkey, RustFS), core schema and migrations, PostgreSQL row-level security
as defense-in-depth on top of application-level RBAC, ADR-01 pooling
discipline, ADR-07 trigger-based audit, six seeded roles, a FastAPI RBAC
dependency, and session-based authentication with mandatory TOTP for
specific roles. Excel import, status-transition endpoints, and the payment
workflow itself were explicitly out of scope — deferred to later modules,
with their tables already existing so those modules build directly on them.

No git remote exists for this project yet; work was committed to a local
repository only (`C:\CodeBase\sirius`), per explicit instruction.
This report was written and committed after that repository was
established — the original module-01 session reported results in chat only
as a stopgap, since committing a report to a repo that didn't exist yet
wasn't possible. Going forward, every module's Definition of Done includes
a committed `reports/module-NN-slug.md`.

## What was built

### Stack (`deploy/`)

`docker-compose.yml` brings up seven services: `postgres` (custom image,
`01-create-app-role.sh` creates the non-superuser `sirius` role on
first init), `pgbouncer` (transaction pooling, `edoburu/pgbouncer`),
`valkey`, `rustfs`, a one-shot `migrate` service, and `api`. Datastores
publish nothing to the host; `api` and `rustfs` publish on plain loopback
(`127.0.0.1`) as an ordinary local-dev habit — ADR-06 (loopback-only
publish / UFW hardening) was explicitly out of scope this module since
there is no public deployment target yet.

### Schema (`api/alembic/versions/0001`–`0005`)

- `role` — six fixed roles, keyed by a stable `code` distinct from the
  human-readable `name`.
- `user` — `role_id`, `totp_secret_encrypted` (Fernet ciphertext),
  `totp_enabled`, `is_active`. Not RLS-scoped (identity axis — see ADR-03).
- `user_backup_code` — ten single-use TOTP backup codes per user, stored as
  argon2id hashes.
- `import_batch` — one row per Excel import run (table only; import logic
  is Module 02's scope).
- `applicant` — `import_batch_id`, `assigned_counselor_id`,
  `current_status` (denormalized read of the latest
  `application_status_event`), `full_name`/`email`/`phone`/`program`/
  `intake_cycle`.
- `application_status_event` — append-only log of every status transition,
  `applicant_id` + `changed_by`.
- `finance_record` — one-to-zero-or-one child of `applicant`
  (`UNIQUE(applicant_id)`), created only once `applicant.current_status`
  reaches `ADMISSION_TAKEN` — enforced by a `BEFORE INSERT` trigger,
  `finance_record_requires_admission_taken()`, not by application code
  alone.
- `payment_claim` — `submitted_by`/`confirmed_by`, both FKs to `user`, with
  a `CHECK (confirmed_by IS NULL OR confirmed_by <> submitted_by)`
  constraint so the two can never resolve to the same user for a given
  claim.
- `audit_log` — one generic table keyed by `table_name` + `record_id`,
  written exclusively by the `write_audit()` trigger.

### Row-level security (ADR-02, ADR-03)

Sirius has no tenancy axis (unlike the GeM precedent this stack's
pooling discipline is modeled on), so RLS here encodes **role-based**
visibility instead: `app.actor_role` decides which roles see a table at
all; `applicant`/`application_status_event` additionally restrict
`ADMISSIONS_COUNSELOR` to rows where `assigned_counselor_id = app.actor_id`.
Every policy uses `FORCE ROW LEVEL SECURITY` and the application connects
as the dedicated non-superuser `sirius` role, never as the
bootstrap `postgres` superuser.

### ADR-01 pooling discipline

`app/core/db.py`'s `open_scoped_session` issues `SET LOCAL` for every RLS
GUC inside one transaction per request; `asyncpg`'s prepared-statement
cache is disabled (`statement_cache_size=0` in `connect_args` and
`?prepared_statement_cache_size=0` on the DSN); Alembic connects direct to
Postgres, bypassing PgBouncer. Every `current_setting()` call in the RLS
policies and the audit trigger is wrapped in `NULLIF(..., '')`.

### ADR-07 trigger-based audit

`write_audit()` fires `AFTER INSERT OR UPDATE OR DELETE FOR EACH ROW` on
every mutable business table, writing table name, record id, action,
before/after JSONB, `actor_id` (from `app.actor_id`), and `client_ip` (from
`app.client_ip`) into `audit_log`. A second trigger,
`audit_log_block_mutation`, blocks UPDATE/DELETE against `audit_log` itself.

### Session auth and RBAC

Argon2id password hashing (`app/core/security.py`), a Valkey-backed session
store with Fernet-encrypted payloads (`app/core/sessions.py`), an
httpOnly/SameSite=Strict cookie with `Secure` gated on
`SESSION_COOKIE_SECURE` (`app/core/cookies.py`), RFC 6238 TOTP via `pyotp`
(`app/core/totp.py`), and a `require_role` FastAPI dependency
(`app/core/deps.py`) demonstrated end-to-end via a minimal `/admin/ping`
route (`app/routers/admin.py`).

## Verification against the live stack

All verification below was run against the real Docker Compose stack —
`docker compose up -d --build` from a clean state, `alembic upgrade head`
through the real `migrate` service, `psql` connected as the ordinary
`sirius` role (never superuser), and real HTTP calls against the
running `api` container on `127.0.0.1:38210` — not code review alone.

### Migrations

`docker compose up migrate` ran all five migrations cleanly from empty
volumes. `\dt+` confirmed all ten tables owned by `sirius`, not
`postgres` (see Defect 1 below).

### RLS isolation

With no `app.actor_role`/`app.actor_id` GUC set at all, every RLS-protected
table returned zero rows (fail-closed). With `app.actor_role =
'ADMISSIONS_MANAGER'`, both a counselor-assigned and an unassigned test
applicant were visible. With `app.actor_role = 'ADMISSIONS_COUNSELOR'` and
`app.actor_id` matching the assigned counselor, only their own applicant
was visible; with a non-matching `app.actor_id`, zero applicants were
visible. `finance_record` was visible to `FINANCE_MANAGER` and correctly
invisible to `ADMISSIONS_COUNSELOR`.

**ADR-01's own reset-value behavior was reproduced live, not just
asserted**: on the same pooled backend, after a transaction that set
`app.actor_role` committed, a fresh query with no `SET LOCAL` at all showed
`current_setting('app.actor_role', true)` returning an empty string, not
NULL — and the very next `applicant` query on that same connection still
correctly returned zero rows (fail-closed), confirming the `NULLIF(...,
'')` wrapping handles the reset-value case correctly rather than raising a
cast error.

### Triggers and constraints

- `finance_record_requires_admission_taken()`: an insert against an
  applicant still at `INQUIRY` was rejected with
  `finance_record can only be created for an applicant whose
  current_status is ADMISSION_TAKEN (was INQUIRY)`; after updating the
  applicant to `ADMISSION_TAKEN`, the identical insert succeeded.
- `payment_claim`'s `ck_payment_claim_distinct_submitter_confirmer` CHECK:
  an insert with `submitted_by = confirmed_by` was rejected by the
  database; an insert with two distinct users succeeded.
- `write_audit()`: every INSERT/UPDATE against `role`, `user`, `applicant`,
  `finance_record`, `payment_claim` produced a corresponding `audit_log`
  row with correct `before`/`after` JSONB (confirmed the applicant's
  `current_status` transition from `INQUIRY` to `ADMISSION_TAKEN` was
  captured exactly) and, when the request-path GUCs were set, the correct
  `actor_id` and `client_ip`.
- `audit_log_block_mutation()`: both UPDATE and DELETE against `audit_log`
  were rejected even when connected as the Postgres **superuser** —
  confirming this is a real trigger-level guarantee, not something RLS
  alone provides (a superuser bypasses RLS entirely but not a trigger).

### Session / TOTP / RBAC over real HTTP

- Login for a non-mandatory-TOTP role (`ADMISSIONS_MANAGER`) returned
  `totp_required: false` and set a working session cookie
  (`HttpOnly; Max-Age=43200; Path=/; SameSite=strict`, `Secure` correctly
  absent since `SESSION_COOKIE_SECURE=false` for local dev).
- Login for a mandatory-TOTP role (`SUPER_ADMIN`) returned
  `totp_required: true, totp_enrollment_required: true`.
- `/auth/totp/enroll/start` returned a real `otpauth://` provisioning URI
  and ten backup codes; `pyotp.TOTP(secret).now()` against the real secret,
  fed to `/auth/totp/enroll/confirm`, succeeded (204) and flipped
  `totp_enabled` to true in the database.
- A fresh login after enrollment correctly showed
  `totp_enrollment_required: false`.
- A wrong TOTP code (`000000`) was rejected (401); a correct live code was
  accepted (204).
- A backup code was accepted once (204) and rejected as
  `"invalid or already-used backup code"` on a second attempt with a fresh
  session — confirmed exactly one of ten `user_backup_code` rows was
  marked `used_at IS NOT NULL` afterward.
- `/auth/logout` destroyed the Valkey session; a subsequent `/auth/me` with
  the same cookie returned 401.
- Login with a wrong password and login with a nonexistent email both
  returned the identical generic `"invalid email or password"` (no user
  enumeration).
- A deactivated user could not log in (`is_active=false` checked at login).
- `require_role`, exercised via `/admin/ping`
  (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`AUDITOR` only): an
  `ADMISSIONS_MANAGER` session reached it (200); an
  `ADMISSIONS_COUNSELOR` session was rejected (403,
  `"insufficient role for this action"`); no session at all was rejected
  (401).

## Real defects found and fixed during this verification

**Defect 1 — migrations ran as the bootstrap superuser, silently defeating
RLS.** `DATABASE_DIRECT_URL` initially connected as `postgres` (the
bootstrap superuser) rather than the `sirius` application role.
Every table Alembic created was therefore owned by `postgres`, and because
Postgres superusers bypass RLS regardless of `FORCE ROW LEVEL SECURITY`,
this is the exact failure mode ADR-02 exists to prevent — the one
previously documented on the GeM project. It was caught immediately by
this module's own live verification: connecting as the ordinary
`sirius` role and attempting `SELECT 1 FROM "role"` failed with
`permission denied for table role`, because `sirius` had never
been granted anything on tables it didn't own. Fixed by changing
`DATABASE_DIRECT_URL` (both `migrate` and `api` services) to connect as
`sirius` even for the direct, non-pooled connection Alembic uses —
confirmed by re-running the migrations from a clean volume and verifying
`\dt+` showed every table owned by `sirius`.

**Defect 2 — `audit_log`'s RLS policy initially blocked the
`write_audit()` trigger's own inserts.** The first draft of the RLS
migration gave `audit_log` the same single `USING`/`WITH CHECK` predicate
(role allowlist: `SUPER_ADMIN`, `AUDITOR`) as every other role-only table.
This is correct for reads but wrong for writes: `write_audit()` fires on
every mutation to *any* audited table regardless of which role performed
it, so an `ADMISSIONS_COUNSELOR` creating an applicant causes the trigger
to insert into `audit_log` on their behalf — and that insert's `WITH
CHECK` was being evaluated against the *actor's* role, not against any
notion of "this insert came from the trusted trigger." The bug surfaced
immediately in live verification: even the `0005_seed_roles` migration
itself (no `app.actor_role` GUC set at all, since migrations run outside a
request) failed with `new row violates row-level security policy for
table "audit_log"` the moment `write_audit()` tried to record the first
seeded role. Fixed by splitting `audit_log`'s policy into two: a `FOR
SELECT` policy keeping the role allowlist, and a `FOR INSERT` policy with
`WITH CHECK (true)` — reads stay restricted to `SUPER_ADMIN`/`AUDITOR`;
the trigger's writes, the only writes `audit_log` structurally accepts
(a second trigger blocks UPDATE/DELETE), are never blocked by a role check
that was never actually about the trigger. Confirmed by re-running
migrations from a clean volume and observing the `payment_claim` insert
(and every prior migration-time insert) correctly appear in `audit_log`.

**Minor defect — `verify_password` did not catch `InvalidHashError`.**
Found while debugging an unrelated test-data issue (a password hash
corrupted by shell escaping in a manual `psql -c` insert): a malformed
stored hash caused `argon2.exceptions.InvalidHashError` to propagate
uncaught out of the login endpoint as a 500, rather than failing closed as
"wrong password" the way a real mismatch does. Fixed by also catching
`InvalidHashError` in `verify_password`.

## Deferred to later modules (per scope)

Excel import, status-transition endpoints, and the payment-claim
submit/confirm workflow itself are explicitly out of scope for this
module. Their tables (`import_batch`, `application_status_event`,
`finance_record`, `payment_claim`) already exist and were verified above
so later modules can build directly on them without further schema
changes.
