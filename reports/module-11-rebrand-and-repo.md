# Module 11: Reset, rebrand, and repository setup — completion report

## Scope

Bring the local stack down with volumes removed for a full data reset,
regenerate every secret in `deploy/.env` from scratch (database password,
session/TOTP encryption keys, RustFS keys), bring the stack back up clean,
and confirm via `psql` that the six roles exist and every other table is
empty. Seed exactly one working login per role, using simple memorable
passwords appropriate for disposable local demo data, and complete real TOTP
enrollment through the actual enrollment endpoint for the three
mandatory-TOTP roles, printing the raw base32 secrets and backup codes
directly to the requester (never committed). Rename the project's
user-facing and documentation-facing identity from "UnivAdmissions" to
Sirius everywhere it appears, leaving the filesystem directory path
untouched. Add the real Forgejo git remote and push the complete existing
commit history. Add standard OSS repository files (LICENSE, README,
CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG) and Forgejo issue/PR
templates. Commit and push everything, and confirm the push landed by
checking the remote.

## What was done

### 1. Full data reset

`docker compose down -v` from `deploy/` removed all three named volumes
(`sirius-postgres-data`, `sirius-valkey-data`, `sirius-rustfs-data`) along
with their containers and the compose network. Docker Desktop itself was not
running at the start of this session and had to be started first
(`com.docker.service` was in a `STOPPED` state) before any compose command
would work.

### 2. Secret regeneration

Every value in `deploy/.env` was regenerated from scratch, reusing nothing
from the prior file:

- `POSTGRES_PASSWORD`, `SIRIUS_DB_PASSWORD` (renamed from
  `UNIVADMISSIONS_DB_PASSWORD` as part of the rebrand — see below): 24 bytes
  of `secrets.token_urlsafe` each.
- `RUSTFS_ACCESS_KEY`: `sirius-` prefix plus 20 hex characters
  (`secrets.token_hex(10)`).
- `RUSTFS_SECRET_KEY`: 32 bytes of `secrets.token_urlsafe`.
- `SESSION_ENCRYPTION_KEY`, `TOTP_ENCRYPTION_KEY`: fresh Fernet keys via
  `cryptography.fernet.Fernet.generate_key()`.

The temporary Python script used to generate these was deleted immediately
after use; it was never committed. All six regenerated values, plus the
per-account TOTP secrets and backup codes described below, were printed
directly in the chat response to the requester, per instruction — none of
them appear in this report or any other committed file.

`deploy/pgbouncer/userlist.txt` (gitignored, holds the plaintext password
PgBouncer uses for its own outbound connection to Postgres) was updated to
match the new `SIRIUS_DB_PASSWORD` exactly — a stale value here would have
broken every pooled `DATABASE_URL` connection while `DATABASE_DIRECT_URL`
(Alembic) kept working, exactly the footgun this project's own
`userlist.txt.example` comment already warns about.

### 3. Clean stack bring-up and verification

`docker compose up -d --build` rebuilt all four custom images (`postgres`,
`pgbouncer`, `migrate`, `api`) against the renamed compose project (`sirius`,
not `univadmissions`) and brought up all five services healthy. `migrate`
ran `alembic upgrade head` cleanly against the empty volumes and exited
successfully before `api` started, per the compose dependency chain.

Verified live via `psql` connected as the ordinary `sirius` role (never the
bootstrap superuser):

- `\dt` confirmed all ten tables exist, every one owned by `sirius`.
- `SELECT code, name FROM "role"` confirmed exactly the six expected roles
  (`SUPER_ADMIN`, `ADMISSIONS_MANAGER`, `ADMISSIONS_COUNSELOR`,
  `FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR`).
- A `UNION ALL` count query across `user`, `user_backup_code`, `applicant`,
  `application_status_event`, `audit_log`, `finance_record`,
  `import_batch`, and `payment_claim` confirmed every one of them at `0`
  rows — a genuinely clean reset, not merely an assumption that
  `down -v` worked.

### 4. Seed users and real TOTP enrollment

One user was inserted per role with an Argon2id password hash generated
using the application's own `app.core.security.hash_password` (run inside
the live `api` container via a temporary script, deleted afterward, never
committed) — not a hand-rolled hash. Emails use the `@sirius.app` domain;
the first attempt used `@sirius.test`, which the API's own
`pydantic[email]` validator correctly rejected as a reserved TLD
("a special-use or reserved name") — a real, if minor, defect caught by
actually calling the endpoint rather than assuming any placeholder domain
would work.

Each of the six logins was verified live against `POST /auth/login`, not
merely inserted and assumed correct:

| Role | Login result |
|---|---|
| `SUPER_ADMIN` | `200`, `totp_required: true`, `totp_enrollment_required: true` |
| `ADMISSIONS_MANAGER` | `200`, `totp_required: false` |
| `ADMISSIONS_COUNSELOR` | `200`, `totp_required: false` |
| `FINANCE_STAFF` | `200`, `totp_required: true`, `totp_enrollment_required: true` |
| `FINANCE_MANAGER` | `200`, `totp_required: true`, `totp_enrollment_required: true` |
| `AUDITOR` | `200`, `totp_required: false` |

For the three mandatory-TOTP roles, real enrollment was completed end to end
through the actual endpoints, not a database-level shortcut:

1. `POST /auth/totp/enroll/start` (with the pending session cookie from
   login) returned a real `otpauth://` provisioning URI and ten backup
   codes for each of `SUPER_ADMIN`, `FINANCE_STAFF`, `FINANCE_MANAGER`.
2. A live six-digit TOTP code was computed from each account's raw base32
   secret (extracted from its own provisioning URI) using `pyotp` inside
   the running `api` container.
3. `POST /auth/totp/enroll/confirm` with that live code returned `204` for
   all three accounts, flipping `totp_enabled=True` server-side.
4. A **fresh** login for `SUPER_ADMIN` was then run to confirm the full
   cycle: `totp_enrollment_required` correctly flipped to `false` on this
   second login. A newly computed live code against `POST /auth/totp/verify`
   returned `204`, and the resulting fully-verified session successfully
   reached the RBAC-protected `GET /admin/ping` route — proving the entire
   chain (login → enroll → confirm → re-login → verify → protected route)
   works end to end against the real running stack, not just that each
   endpoint individually returns 2xx in isolation.

Every raw TOTP secret and its ten backup codes were printed directly in the
chat response, framed explicitly as values to manually add to an
authenticator app before a live demo rather than relying on a live QR scan —
per instruction, none of this appears in this report or anywhere else
committed.

All temporary helper scripts (`_hash_gen.py`, `_totp_codes.py`,
`_seed_users.sql`) and cookie-jar files used during this verification were
deleted from both the `api`/`postgres` containers and the host repository
before committing; `git status` was checked afterward to confirm no scratch
artifact remained.

### 5. Rebrand: UnivAdmissions → Sirius

Renamed the project's user-facing and documentation-facing identity
everywhere it appeared, confirmed by an exhaustive case-sensitive and
case-insensitive repository search after the pass (zero remaining matches
for `univadmissions` in any casing):

- **Docker Compose**: project name (`name: sirius`), network
  (`sirius-net`), volumes (`sirius-postgres-data` etc.), the `POSTGRES_DB`
  name, and every `DATABASE_URL`/`DATABASE_DIRECT_URL` connection string.
- **Postgres**: the application role itself renamed from `univadmissions` to
  `sirius` in `01-create-app-role.sh`, since this is a from-scratch reset
  with no existing data or scripts depending on the old role name persisting
  — a genuinely clean rename, not a compatibility shim.
- **PgBouncer**: `pgbouncer.ini`'s `[databases]` entry and both
  `userlist.txt`/`userlist.txt.example`.
- **API**: `FastAPI(title=...)`, the TOTP `ISSUER_NAME` (what an
  authenticator app displays), the session cookie name
  (`univadmissions_session` → `sirius_session`, both the constant in
  `cookies.py` and three hardcoded duplicate reads in `auth.py`),
  `pyproject.toml`'s `name`/`description` fields.
- **Frontend**: the `<title>` tag (previously the Vite default, "frontend",
  never actually branded at all until now), the login page's displayed app
  name and email placeholder, the app shell header text,
  `package.json`'s `name` field (`frontend` → `sirius-frontend`), and
  `package-lock.json` regenerated via `npm install --package-lock-only` so
  its own `name` fields stay consistent with `package.json` rather than
  hand-edited out of sync.
- **Docs and reports**: every ADR and every prior module's completion report
  updated in place, including one report's own record of the (now-obsolete)
  local-only clone path, which was recorded as `C:\CodeBase\univadmissions`
  at the time — updated to reflect this rename since it is now inaccurate
  as project documentation, not because the actual directory moved.

**The filesystem directory itself was deliberately left untouched** per
explicit instruction — the working directory for this entire session
remained `C:\CodeBase\Sirius` throughout (it was already named `Sirius` on
disk before this module began; only the project's own internal/documentation
identity referred to it as "UnivAdmissions"). Nothing in this module's
verification surfaced a reason that assumption is untenable: no script,
config file, or CI definition in this repository hardcodes an absolute path
containing the old project name that would need the directory itself to
move.

### 6. Git remote and push

Added `origin` pointing at `https://git.vrip7.com/gamecooler19/Sirius.git`
(no remote existed on this repository before this module — Module 01's own
report explicitly flagged this as an open item: "No git remote exists for
this project yet ... per explicit instruction"). The stored Windows
credential-manager OAuth token for `git.vrip7.com` had expired
(`Credentials are incorrect or have expired`); clearing it via `cmdkey
/delete` and retrying `git push` triggered a fresh OAuth grant flow (handled
by the host's own credential helper/browser integration, not by this agent
directly), after which the push succeeded.

### 7. Repository hygiene files

Added at the repository root: `LICENSE` (MIT, copyright Pradyumn Tandon,
2026), a fully rewritten `README.md` (real problem statement, actual tech
stack, setup instructions matching `deploy/docker-compose.yml` as it exists
today, and an honest module-by-module build history), `CONTRIBUTING.md`
(this project's actual Crux-scopes/Jcode-executes/live-verification
workflow, not a generic template), `CODE_OF_CONDUCT.md` (standard
Contributor Covenant v2.1), `SECURITY.md` (a vulnerability-reporting policy
specific to the real sensitivity here — applicant PII and payment/finance
data), and `CHANGELOG.md` summarizing what each of the ten prior modules and
their follow-up verification rounds actually delivered, in order.

Confirmed via Forgejo's own published documentation
(`forgejo.org/docs/latest/user/repository/issue-pull-request-templates/`)
that Forgejo checks `.forgejo` before `.gitea` before `.github` before
`docs` for template directories, and added templates under `.forgejo/`
accordingly (Forgejo's own convention, not GitHub's `.github` path):
`.forgejo/ISSUE_TEMPLATE/bug_report.yaml`,
`.forgejo/ISSUE_TEMPLATE/feature_request.yaml`,
`.forgejo/ISSUE_TEMPLATE/config.yml` (disables blank issues in favor of the
two templates, plus a contact link pointing at `SECURITY.md` for
vulnerability reports), and `.forgejo/pull_request_template.md` (a
checklist reflecting this project's own live-verification and
secret-hygiene discipline, not a generic PR template).

## Verification against the live stack

- `docker compose ps` after bring-up: all five services reported healthy
  (`postgres`, `pgbouncer`, `valkey`, `rustfs` healthy; `api` reached
  healthy shortly after `migrate` exited `0`).
- `curl http://127.0.0.1:38210/healthz` → `{"status":"ok"}`.
- `psql` role/table-emptiness checks as described in section 3, run against
  the real container, not inferred from migration success alone.
- All six logins and the full three-role TOTP enrollment/verification cycle
  described in section 4, run against real HTTP endpoints on the running
  `api` container.
- `git ls-remote origin` after pushing returned
  `1e24f54ab31f8f5e2e60bb127c620148fef967e2` for both `HEAD` and
  `refs/heads/master`, matching `git rev-parse HEAD` on the local
  repository exactly — the push genuinely landed, confirmed by querying the
  remote directly rather than trusting `git push`'s own exit code alone.
  `git log --oneline | wc -l`-equivalent counts matched at 17 commits on
  both sides (Modules 01 through 11, plus one prior follow-up-only commit),
  confirming the complete existing history was pushed, not a shallow or
  partial history.

## What was intentionally not done

- No user-facing "signup" or admin-console user-creation flow exists yet, so
  the six seed accounts were inserted directly against the `user` table
  (with a real Argon2id hash from the application's own hasher) rather than
  through an API endpoint — there currently is no such endpoint to use.
- The Postgres/PgBouncer application role itself was renamed from
  `univadmissions` to `sirius` as part of this module, made safe only
  because this is a full reset with no data or external script depending on
  the old name surviving. This is called out explicitly since it is a
  behavioral rename, not purely cosmetic — any local script outside this
  repository that hardcoded `univadmissions` as a `psql` username against a
  previously running instance would need updating.

## Cleanup

All temporary secret-generation and TOTP-helper scripts, the SQL seed file,
and every cookie-jar file created during this module's live verification
were deleted from both the `api`/`postgres` containers and the host
repository before committing. `git status` was checked immediately before
each commit to confirm no scratch artifact, and separately to confirm
`deploy/.env` and `deploy/pgbouncer/userlist.txt` — both holding the
regenerated real secrets — remained gitignored and untracked throughout,
never staged.
