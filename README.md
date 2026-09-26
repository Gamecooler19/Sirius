# Sirius

Sirius is an admissions and finance tracker built for Illinois Tech Mumbai's
own workflow: getting an applicant from "imported from a spreadsheet" to
"admission taken," while finance staff independently track fee dues and
payment claims against the same applicant, with a real maker-checker
approval step and an append-only audit trail underneath both sides.

It is a small, real system built to answer a specific set of hard questions
correctly rather than a broad platform: does row-level security actually do
anything once a connection pooler is in the picture, does a maker-checker
rule hold when the maker and the checker are the same person, and can a
six-role RBAC system with mandatory two-factor authentication be built
without hand-waving the enrollment flow.

## The problem

Illinois Tech Mumbai's admissions and finance teams needed one shared system,
not two disconnected spreadsheets, where:

- Admissions staff track applicants through a fixed pipeline
  (`IMPORTED` → `APPLIED` → `IN_PROCESS` → `ON_HOLD` /
  `ADMISSION_OFFERED` → `ADMISSION_TAKEN` / `REJECTED` / `WITHDRAWN`),
  bulk-imported from an Excel sheet as the common intake format.
- Finance staff track each applicant's fee balance and payment claims
  independently of admissions status, with every claim requiring a second
  person's confirmation before it counts — a finance staff member can
  submit a claim they made themselves, but cannot also be the one who
  confirms it.
- Six distinct roles (`SUPER_ADMIN`, `ADMISSIONS_MANAGER`,
  `ADMISSIONS_COUNSELOR`, `FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR`) see
  different slices of the same data, an admissions counselor never sees
  finance data and vice versa, and a counselor only ever sees their own
  assigned applicants.
- Every mutation is attributable: who changed what, when, and from where,
  recorded somewhere no application code path can quietly skip.
- The three roles with the most sensitive access (`SUPER_ADMIN`,
  `FINANCE_STAFF`, `FINANCE_MANAGER`) authenticate with mandatory TOTP
  two-factor, not password alone.

## Tech stack

**Backend** — FastAPI (Python 3.12, async throughout), SQLAlchemy 2.x async
ORM, Alembic migrations, PostgreSQL 17 behind PgBouncer in transaction
pooling mode, Valkey (Redis-compatible) for session storage, RustFS
(S3-compatible object storage, provisioned for future import-artifact
storage). Argon2id for password and backup-code hashing, Fernet (symmetric)
encryption for session payloads and TOTP secrets at rest, `pyotp` for RFC
6238 TOTP.

**Frontend** — Vite + React 19 + TypeScript, Mantine as the sole component
library, Tailwind CSS (Preflight disabled so it doesn't fight Mantine's base
styles), TanStack Query v5 for all server state, Phosphor Icons, `qrcode.react`
for rendering TOTP provisioning URIs as scannable QR codes during enrollment.

**Access control** — Role-based access control enforced at the application
layer (a FastAPI dependency chain: session → RBAC → RLS-scoped DB session),
*and* PostgreSQL row-level security as defense-in-depth underneath it, with
`FORCE ROW LEVEL SECURITY` so the owning application role is actually
subject to its own policies rather than silently bypassing them — a defect
class this project's own ADR-02 documents finding and fixing for real, not
hypothetically.

## Setup

Everything runs through Docker Compose; there is no supported way to run the
stack directly against a host-installed Postgres/Redis.

**Prerequisites**: Docker with Compose v2, and nothing else — the API and
frontend both build inside containers.

```bash
cd deploy
cp .env.example .env
# Edit .env: set real values for POSTGRES_PASSWORD, SIRIUS_DB_PASSWORD,
# RUSTFS_ACCESS_KEY, RUSTFS_SECRET_KEY, SESSION_ENCRYPTION_KEY, and
# TOTP_ENCRYPTION_KEY. Generate the two Fernet keys with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

cp pgbouncer/userlist.txt.example pgbouncer/userlist.txt
# Edit userlist.txt: replace "changeme" with the exact same value as
# SIRIUS_DB_PASSWORD above.

docker compose up -d --build
```

This brings up six services: `postgres` (custom image that creates the
non-superuser `sirius` application role on first init), `pgbouncer`
(transaction pooling), `valkey`, `rustfs`, a one-shot `migrate` service that
runs `alembic upgrade head` and exits, and `api`. The API is reachable at
`http://127.0.0.1:38210` once `migrate` completes successfully — `api` is
configured to wait for it.

For the frontend, in a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://127.0.0.1:5173`, already included in the
backend's default `CORS_ORIGINS`.

To reset all local data (drop every volume and start over):

```bash
cd deploy
docker compose down -v
docker compose up -d --build
```

Six roles are seeded automatically by migration `0005_seed_roles`. No user
accounts are seeded by default — create them directly against the `user`
table (password hashed with `app.core.security.hash_password`) for local
development, since there is currently no signup flow or admin-console user
creation endpoint.

## How this was built

Sirius was built module by module, each module scoped narrowly, implemented,
and verified against the real running stack (not code review or mocks)
before the next module started. See `CHANGELOG.md` for what each of the ten
modules and their follow-up verification rounds actually delivered, and
`reports/module-NN-*.md` for each module's full completion report, including
the real defects each module's own live verification found and fixed.

In short:

1. **Module 01** laid the foundation — the Compose stack, schema, row-level
   security, trigger-based audit, seeded roles, and TOTP-aware session auth.
2. **Modules 02–03** built the two core workflows: applicant status
   transitions plus Excel import, then the payment-claim maker-checker
   workflow.
3. **Modules 04–05** added read endpoints and cross-cutting finance
   reconciliation on top of data the earlier modules already created.
4. **Modules 06–10** built the frontend, one screen at a time, each wired to
   real backend endpoints from day one — never a mocked API layer.
5. **Module 11** (this rebrand) reset all local secrets and data from
   scratch, renamed the project from its working name ("UnivAdmissions") to
   Sirius, and made the repository ready to push to a real remote for the
   first time.

Every module's report documents live defects found by actually running the
stack and exercising it — connecting through PgBouncer as the unprivileged
application role, driving real HTTP requests against a running container,
computing real TOTP codes from a freshly enrolled secret — rather than
defects found by reading the code a second time.

## Repository layout

```
api/        FastAPI application, Alembic migrations, business logic
frontend/   Vite + React frontend
deploy/     Docker Compose stack, Postgres/PgBouncer init and config
docs/adr/   Architecture Decision Records for the non-obvious infra choices
reports/    One completion report per module, in order
```

## License

MIT — see `LICENSE`.
