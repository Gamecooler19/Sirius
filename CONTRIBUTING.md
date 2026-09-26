# Contributing to Sirius

This project was not built the way most repositories are built, and this
document describes the actual process used, not a generic contribution
template. If you're picking this project up, understanding this workflow
will help you understand why the code and the `reports/` directory look the
way they do.

## The workflow: Crux scopes, Jcode executes, live verification decides

Every module of this project (see `CHANGELOG.md` and `reports/`) followed
the same three-step loop:

1. **Crux scopes.** Before any code was written, the module's scope was
   written down explicitly and narrowly: which endpoints, which schema
   changes, which UI screens, and — just as importantly — what was
   deliberately *out* of scope and deferred to a later module. Module 01's
   own report is a clear example: it built the schema and auth foundation
   but explicitly deferred status-transition and payment-workflow endpoints
   to Module 02, leaving the tables in place so the next module could build
   directly on them without a schema migration mid-flight.

2. **Jcode executes.** An agent (Jcode) implemented the scoped module:
   migrations, models, endpoints, frontend screens, wiring — end to end for
   that module's scope, not a partial stub to be finished by hand later.

3. **Live verification decides whether the module is actually done.** This
   is the part that most distinguishes this project's process from a
   typical PR review. A module was not considered complete because the code
   looked correct. It was considered complete when it had been exercised
   against the *real, running* Docker Compose stack:
   - Real `psql` connections through PgBouncer as the ordinary,
     unprivileged `sirius` role — never as the bootstrap superuser —
     to confirm row-level security actually restricts what that role can
     see, not merely that a policy exists in `\d+` output.
   - Real HTTP requests (`curl`, or a real browser session for frontend
     modules) against the running `api` container, not a mocked backend or
     `jsdom`.
   - Real `.xlsx` files built with `openpyxl` for the Excel-import module,
     not a hand-crafted fixture shaped to only exercise the happy path.
   - Real TOTP codes computed live from a freshly provisioned secret for
     any auth-related verification, not an assumption that "the library is
     surely correct."

   Every module's report documents this verification explicitly, including
   the exact commands run and the exact responses observed. Several modules
   (see the "Real defects found and fixed" sections in `reports/module-01`,
   `-02`, `-03`, `-06`, `-09`) found genuine bugs this way that a code review
   alone would not have caught — for example, Module 01's live verification
   caught migrations running as the Postgres bootstrap superuser rather than
   the intended non-superuser role, which would have silently defeated every
   row-level security policy in the schema despite the code looking correct.

## Follow-up verification rounds

Several modules have a second "Follow-up verification" section in their
report, added after the module's initial report was written. These exist
because live verification is itself gradeable: a module's original
verification might have exercised one filter at a time but never two
filters combined, or verified a query's happy path but never its zero-row
edge case. Follow-up rounds went back and closed those specific gaps against
the same live stack, using the same discipline — no new code was ever
written to make a follow-up check pass to score, only fixed if verification
found a real defect.

## What this means for you as a contributor

If you're adding a new module or fixing a bug in an existing one, follow the
same loop:

1. **Scope it narrowly and write the scope down** in a new
   `reports/module-NN-your-slug.md` (or add a section to the relevant
   existing report if it's a fix, not a new module) before writing code.
2. **Implement the full scope**, not a partial version deferred to "later."
3. **Verify against the real running stack**, not against your own
   assumption that the code is correct. Bring up `deploy/docker-compose.yml`
   for real, connect through PgBouncer as the ordinary `sirius` role (never
   the bootstrap superuser) if your change touches RLS, drive real HTTP
   requests against the running `api` container, and use a real browser
   session (not a mocked fetch) for any frontend change.
4. **Document what you actually verified**, including the exact commands
   and responses, in the module's report — not "should work" or "tests
   pass," but what you personally observed running against the real stack.
5. **Clean up before committing.** Any temporary helper script, scratch
   `.xlsx` fixture, or debug print used only during verification gets
   deleted from both the container and the host before the commit — check
   `git status` for stray artifacts.

## Architecture Decision Records

Non-obvious infrastructure decisions (why PgBouncer needs `SET LOCAL` and
never plain `SET`, why the application connects as a non-superuser role, why
row-level security here encodes role-based visibility rather than
multi-tenancy, why the audit trail is a database trigger rather than an
application-level helper) are documented in `docs/adr/`, each with the real
context, the decision, and the consequences accepted. If you're making a
comparable infrastructure decision, add an ADR rather than only a code
comment — the "why," not just the "what," is what future contributors and
Jcode sessions actually need.

## Secrets

Never commit `deploy/.env`, `deploy/pgbouncer/userlist.txt`, or any real
credential, TOTP secret, or backup code to this repository. Both files are
gitignored; only their `.example` counterparts are committed. If you
regenerate secrets for local development, treat the values as disposable
local-demo credentials, never something to reuse in a shared or production
environment.
