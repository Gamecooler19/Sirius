# Module 23: Complete reset and single SUPER_ADMIN seed — completion report

## Scope

Bring the stack down with volumes removed for a full data reset, exactly
like Module 11's own reset — every applicant, finance record, demo
account, and test artifact from every module so far gone. Add one new
migration, next in sequence, that seeds exactly one user (`SUPER_ADMIN`
Pradyumn Tandon, `ptandon3@hawk.illinoistech.edu`), with no password or
password hash ever a literal in the migration file, `totp_enabled=False`
by construction so the normal enrollment flow handles TOTP on first
login, and an idempotent insert that only fires once against a fresh
database. Bring the stack back up clean, run migrations, and verify
against the live stack via `psql` and a real login + TOTP enrollment
through the actual frontend.

## What was done

### 1. New migration: `0016_seed_superadmin`

Added `api/alembic/versions/0016_seed_superadmin.py`, next in sequence
after `0015_finance_fee_due`, following `0005_seed_roles`'s own
"seed once, first-run only" shape:

- **Idempotency.** A `SELECT` against `"user"` by the seed's own fixed
  email runs before anything else, including reading the environment —
  a re-run against a database that already has this seed is a genuine
  no-op with no environment variable required at all, matching
  `0005_seed_roles`'s own re-run contract. A plain conditional `INSERT`
  was used rather than `ON CONFLICT (email) DO NOTHING`, since the
  latter would silently swallow the one case worth distinguishing from
  "already seeded correctly": a different row somehow already occupying
  this exact email with different data.
- **No password or hash as a literal.** `SUPERADMIN_INITIAL_PASSWORD`
  is read from the environment (`os.environ`) at migration-run time
  only — the migration raises immediately, before touching the
  database, if it is unset on a fresh (not-yet-seeded) database. It is
  hashed with `app.core.security.hash_password`, the exact same
  Argon2id `PasswordHasher` instance every other password/backup-code/
  reset-token hash in this codebase already uses — not a hand-rolled or
  differently-parameterized hash. `alembic/env.py` already imports from
  `app.*` for `Settings`, so importing `app.core.security` here follows
  that same established precedent. Only the resulting hash is ever
  written to `user.password_hash`; the plaintext value is used exactly
  once, in-process, and never persisted by this migration.
- **`totp_enabled=False` by construction**, matching `POST /users`' own
  reasoning verbatim (see that route's own docstring, quoted in this
  migration's docstring too): the migration does not provision a TOTP
  secret or pre-confirm enrollment in any way, leaving
  `user.totp_enabled`'s own `server_default` (`false`) to do the work,
  so `POST /auth/login`'s existing `totp_enrollment_required` branch
  drives this account through the real `/auth/totp/enroll/start` +
  `/confirm` flow on its first login, identical to any other
  mandatory-TOTP account this project has ever created.
- **`is_active=True`.**
- **`activated_at` left `NULL`** — the same "has this account completed
  the real self-service activation flow" signal `POST /users`-created
  accounts start with; unlike an admin-created account, this seed does
  have a real, immediately-usable password from the moment the
  migration runs, so a working login while `activated_at` stays `NULL`
  is consistent with that column's own documented, display-only
  purpose, not a contradiction.
- `downgrade()` deletes the seeded row by email — and, as of this
  module's own follow-up verification (see "A real defect found and
  fixed" below), the account's own `user_backup_code` rows first.

### 1a. A real defect found and fixed during this module's own follow-up verification

`downgrade()`'s first version deleted only the `"user"` row. That is
correct for a database where the seed was inserted and never touched
again, but this module's own live verification had, by this point,
actually completed real browser-driven TOTP enrollment against the
seeded account (see section 6 below) — giving it ten real
`user_backup_code` rows. `user_backup_code_user_id_fkey` (migration
0002) carries no `ON DELETE CASCADE`, so re-running
`alembic downgrade 0015_finance_fee_due` against that same database hit
a real, live `asyncpg.exceptions.ForeignKeyViolationError`: "update or
delete on table `user` violates foreign key constraint
`user_backup_code_user_id_fkey`" — not a hypothetical, the actual
downgrade command failed with this exact error on the actual running
stack. Alembic's own transactional DDL rolled the failed attempt back
cleanly (confirmed via `psql`: the database was left exactly at head,
one user row, no partial state), but the `downgrade()` path itself was
still genuinely broken for any database where this account had ever
been used.

**Fixed** by deleting the account's own `user_backup_code` rows (by
`user_id`, resolved via a subquery keyed on this migration's own fixed
seed email — never a second hardcoded id) before deleting the `"user"`
row itself — the same "verify before you rely on an omission" standard
`0015_finance_fee_due`'s own report already established for an
analogous live ordering defect. `audit_log.actor_id` also references
`"user"` with no cascade, but was checked live (`SELECT actor_id, count(*)
FROM audit_log GROUP BY actor_id` with `app.actor_role` set to see past
RLS) and confirmed `NULL` for every row this account's own self-service
auth actions ever produced — not a live blocker, so no matching cleanup
was needed there.

**Re-verified live after the fix**, rebuilding the `migrate` image first
(the running container still held the pre-fix file):
`alembic downgrade 0015_finance_fee_due` against the same database (with
its real, ten-row `user_backup_code` set still in place) completed
without error; `psql` confirmed both the `user` row and all ten
`user_backup_code` rows were gone. `alembic upgrade head` immediately
after re-created the seed account correctly.

Because this defect was found mid-verification, **the full reset and
bring-up were repeated a second time** (`docker compose down -v` /
`up -d --build`) against the corrected migration file, so the delivered
final state was produced by the fixed code end to end, not patched in
place after the fact. Every verification step in this report below
(psql row counts, real login, real TOTP enrollment through the actual
UI, the second HTTP-only login+verify+protected-route cycle) was
re-run against that final, fixed-migration bring-up — the numbers and
user id shown below are from that final run.

### 2. `SUPERADMIN_INITIAL_PASSWORD` generation and wiring

Generated with `secrets.token_urlsafe(24)`, the same generation method
Module 11 already used for every other secret in this stack. Added to:

- `deploy/.env` (gitignored, never committed) — with a comment
  explaining its scope, matching every other secret's own commented
  entry in that file.
- `deploy/.env.example` (committed) — a `changeme-...` placeholder plus
  the exact generation command, matching every other secret's own
  example entry.
- `deploy/docker-compose.yml`'s `migrate` service `environment:` block
  only — the `api` service deliberately does not receive this variable
  at all, since no request-path code ever needs it once the seed
  migration has run.

### 3. Full data reset

`docker compose down -v` from `deploy/` removed all three named volumes
(`sirius-postgres-data`, `sirius-valkey-data`, `sirius-rustfs-data`)
along with every container and the compose network — the identical
command Module 11's own reset used.

### 4. Clean bring-up and migration run

`docker compose up -d --build` rebuilt all four custom images and
brought up every service. `migrate` ran `alembic upgrade head` cleanly
from `0001_baseline` through the new `0016_seed_superadmin`, exit code
`0`, before `api` started (per the existing compose dependency chain).

### 5. Idempotency and downgrade/upgrade round-trip — verified live, not just reasoned about

- Re-ran `docker compose run --rm migrate alembic upgrade head` against
  the already-migrated database: no error, `SELECT count(*) FROM
  "user"` still returned exactly `1` afterward — the idempotency guard
  works against a real re-run, not merely in the abstract.
- Ran `alembic downgrade 0015_finance_fee_due`: the seeded row was
  genuinely deleted (`count(*) = 0`), confirming `downgrade()` is a
  real, working inverse.
- Ran `alembic upgrade head` again: the row was correctly re-inserted
  with the same email/name, confirming the full lifecycle (seed →
  idempotent re-run → downgrade → re-upgrade) round-trips cleanly
  against the real stack.

## Verification against the live stack

### `psql`, connected as the ordinary `sirius` role

- `\dt`: all twelve tables present, every one owned by `sirius`.
- `SELECT id, email, full_name, role_id, totp_enabled, is_active,
  activated_at FROM "user"` returned **exactly one row**:
  `ptandon3@hawk.illinoistech.edu`, `Pradyumn Tandon`,
  `totp_enabled=f`, `is_active=t`, `activated_at` NULL (this state, and
  the `totp_enabled=t`/`activated_at` NULL state shown later in this
  report, both reflect the same account at two different points in the
  same final, fixed-migration bring-up — before and after this
  verification round's own TOTP enrollment).
- `password_hash` was read directly and checked independently against
  `app.core.security.verify_password` (the app's own function, not a
  re-implementation) inside the running `api` container:
  `verify_password('<the generated password>', <stored hash>)` returned
  `True`; the same call with an arbitrary wrong string returned `False`
  — the stored hash is a real, working Argon2id hash of the exact
  generated password, not merely a plausible-looking string. The stored
  value itself (`$argon2id$v=19$m=65536,t=3,p=4$...`) also matches the
  exact `time_cost=3`/`memory_cost=65536`/`parallelism=4` parameters
  `app/core/security.py`'s own `PasswordHasher()` uses, confirming no
  separate/weaker hasher was used.
- `docker compose exec api env` confirmed `SUPERADMIN_INITIAL_PASSWORD`
  is genuinely absent from the `api` service's own environment (no
  match), while `docker compose run --rm migrate env` confirmed it is
  present there — the docker-compose scoping described above is real,
  not just written in a comment nobody checked.
- Joining that row to `"role"` confirmed `role_code = SUPER_ADMIN`.
- `SELECT code, name FROM "role"` confirmed all six expected roles seeded
  correctly by `0005_seed_roles`, unaffected by the new migration.
- A `UNION ALL` count query across `user`, `applicant`,
  `application_status_event`, `finance_record`, `import_batch`,
  `payment_claim`, `push_subscription`, `password_reset_token`, and
  `user_backup_code` (`app.actor_role` unset, so RLS-scoped tables read
  as zero rows by their own fail-closed design) confirmed `user = 1`
  and every other table `= 0` — no other seed account, applicant, or
  finance record survived the reset. `audit_log`, re-queried with
  `app.actor_role` set to `SUPER_ADMIN` to see past RLS, showed only
  the role-seed inserts and this module's own single-user seed/
  enrollment activity — nothing pre-existing.

### Real login through the actual login form, and real TOTP enrollment through the actual UI

Opened `http://127.0.0.1:5173/login` in a real browser (not a scripted
API-only flow) and typed the generated email/password into the real
form fields, then clicked the real "Sign in" button:

1. Login succeeded and the app correctly routed to the mandatory-TOTP
   enrollment screen (`SUPER_ADMIN` is a `MANDATORY_TOTP_ROLES`
   member), showing a real QR code and ten real backup codes generated
   by `POST /auth/totp/enroll/start`.
2. A live six-digit TOTP code was computed from the account's own raw
   base32 secret (retrieved via the same authenticated pending session,
   the identical method Module 11 used) with `pyotp` inside the running
   `api` container.
3. That live code was typed into the real six-box PIN input on the
   enrollment screen, and the real "Confirm enrollment" button was
   clicked — the app navigated straight to the authenticated Home
   dashboard, header showing "Pradyumn Tandon · SUPER_ADMIN".
4. The real, authenticated **Users** page was opened next: it shows
   exactly one row — `ptandon3@hawk.illinoistech.edu`, `Pradyumn
   Tandon`, role `SUPER_ADMIN`, status `ACTIVE` + `PENDING ACTIVATION`
   (expected — `activated_at` is `NULL` by design, see above), 2FA
   `ENROLLED`.

**Full cycle re-confirmed a second time via direct HTTP against the
same running stack** (the same class of check Module 11's own report
used to prove the chain end to end, not merely each endpoint in
isolation):

- A **fresh** `POST /auth/login` call returned
  `totp_enrollment_required: false` (flipped correctly from `true`
  before enrollment) — confirming `user.totp_enabled` is genuinely
  `True` in the database now, not just true in the one browser session.
- A freshly computed live code against `POST /auth/totp/verify`
  returned `204`.
- The resulting fully-verified session reached the RBAC-protected
  `GET /users` route (`200`), returning the same single row confirmed
  in `psql` — `totp_enabled: true`, `is_active: true`.

`audit_log` (queried with `app.actor_role = SUPER_ADMIN`) independently
confirms the same story: one `user` `INSERT` for the seed row, followed
by `UPDATE`s recording the enrollment-confirm and each `reset-totp`-
style backup-code regeneration this verification round exercised (the
browser's own confirm, plus this report's own re-verification calls),
each paired with the corresponding `user_backup_code` `INSERT`/`DELETE`
rows — a real, append-only trail of exactly what this module did, not
merely an assertion that it worked.

## Cleanup

All scratch cookie-jar files (`cookies.txt`, `cookies2.txt`) and a
temporary login-response file created during this module's own live
verification were deleted from the host repository before committing;
`git status` was checked immediately before commit to confirm none
remained and that `deploy/.env` stayed gitignored and untracked
throughout, never staged.

## What was intentionally not done

- No other account of any kind was seeded — per this module's own
  explicit scope, the system now has exactly one working login. Any
  further testing needs an account created manually through this
  account's own `POST /users` admin flow (Module 15), not another
  direct-insert seed.
- `deploy/pgbouncer/userlist.txt` was not touched — this module did not
  rotate `SIRIUS_DB_PASSWORD` or any other pre-existing secret, only
  added the new `SUPERADMIN_INITIAL_PASSWORD`, so that file's own
  Module 11-era value remains correct and untouched.

The generated `SUPERADMIN_INITIAL_PASSWORD` value itself is not
reproduced anywhere in this report, per this project's own standing
"never commit a secret" rule — it was printed directly in the chat
response to the requester and written only to the gitignored
`deploy/.env`.
