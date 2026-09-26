# Security Policy

Sirius handles two categories of genuinely sensitive data: applicant
personally identifiable information (names, contact details, admissions
history) and payment/finance records (fee balances, payment claims,
reference numbers). This policy exists to make sure a real vulnerability
report reaches someone who can act on it, quickly, without going through a
public issue tracker first.

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.** Public issues
are appropriate for bugs that don't expose data or bypass access control;
anything that could let one role read another role's data, bypass
authentication or TOTP, forge or replay a session, or exfiltrate applicant
PII or payment data should be reported privately.

To report a vulnerability, contact the maintainer directly:

- **Pradyumn Tandon**, via the contact method listed on their profile at the
  Forgejo instance hosting this repository (`git.vrip7.com`), or by opening
  a private security advisory on the repository if the Forgejo instance
  supports it.

Please include:

- A clear description of the vulnerability and its impact (what data or
  access it exposes, and to whom).
- Steps to reproduce it, ideally against a local `docker compose up`
  instance rather than any shared environment.
- Any relevant request/response payloads, with real secrets, session
  cookies, or TOTP codes redacted.

## What to expect

- **Acknowledgment**: within 5 business days of the report.
- **Initial assessment**: within 10 business days, including whether the
  report is confirmed, its severity, and an expected timeline for a fix.
- **Disclosure**: coordinated with the reporter. We ask that you give us a
  reasonable window to ship a fix before any public disclosure, and we
  commit to not sitting on a confirmed report indefinitely.

## Scope

In scope:

- The `api/` FastAPI application: authentication, session handling, TOTP
  enrollment/verification, RBAC (`require_role`), row-level security
  policies, the Excel-import endpoint, and any endpoint touching
  `applicant`, `finance_record`, or `payment_claim` data.
- The `frontend/` application, specifically anywhere it might leak session
  state, mishandle the TOTP enrollment flow, or fail to respect a
  server-side role gate.
- The `deploy/` Docker Compose stack configuration itself, including
  PgBouncer auth handling and Postgres role privileges.

Out of scope:

- Third-party dependencies with no Sirius-specific misuse (report those
  upstream) unless Sirius's own usage of them introduces the vulnerability.
- Denial-of-service reports against a local development stack with no
  production deployment target.
- Issues requiring physical access to a machine already running the stack.

## Known design boundaries (not vulnerabilities)

A few things are deliberate design decisions, documented in `docs/adr/`, not
gaps to report:

- Row-level security in this project encodes **role-based** visibility, not
  multi-tenancy (ADR-03) — there is no tenant-isolation guarantee to break,
  because there is no tenant axis.
- `SESSION_COOKIE_SECURE` is `false` in local development by design (plain
  HTTP, no browser stores a `Secure` cookie otherwise) — this must be `true`
  in any real deployment, and reporting "the cookie isn't marked Secure" in
  the default local dev configuration is a known, intentional tradeoff, not
  a new finding.
- Backup codes and passwords are both hashed with Argon2id (the same
  hasher), and TOTP secrets are Fernet-encrypted at rest with a key distinct
  from the database itself — a database dump alone does not hand over live
  TOTP seeds. Reports about encryption key management for a *local
  development* deployment (where the key sits in a gitignored `.env` file
  on the same host) are a known tradeoff specific to local dev; a real
  deployment would source that key from a proper secret manager.
