# ADR-02: The application connects as a dedicated non-superuser role

## Status

Accepted

## Context

Row-level security's `FORCE ROW LEVEL SECURITY` only matters for the table owner —
a non-owner without `BYPASSRLS` is already subject to RLS regardless of `FORCE`.
Postgres superusers and roles with `BYPASSRLS` skip RLS checking entirely,
independent of any policy or `FORCE` flag. This is exactly the failure mode that
silently defeated row-level security on GeM: the application was connecting as the
bootstrap superuser, so every RLS policy in that schema was syntactically correct
and completely inert — `\d+` showed policies attached, `psql` showed RLS enabled,
and none of it did anything, because the connecting role bypassed the check
before any policy predicate was ever evaluated. The gap went undetected until a
dedicated audit connected as an ordinary role and found every table readable
regardless of tenant/actor scope.

## Decision

1. **Two distinct roles from the start.** `POSTGRES_USER` (the bootstrap
   superuser Postgres's own init process requires) is `postgres`, never the
   application's own role name. Postgres will not let you strip `SUPERUSER` from
   the role currently running the init script, so the bootstrap role and the
   application role must be different roles from the very first migration, not
   something to "tighten later."
2. **The application role (`univadmissions`) is created explicitly
   `NOSUPERUSER NOBYPASSRLS`**, stated even though both are Postgres defaults for
   a freshly created role — the guarantee must not depend on that default
   silently changing in a future Postgres version or a copy-pasted role-creation
   script.
3. **The application role owns the `public` schema**, not merely `CREATE` on it.
   Migrations run as this role and create every table as this role, so `FORCE ROW
   LEVEL SECURITY` is the thing actually doing the work, rather than ordinary
   non-ownership incidentally doing it.
4. **Verification is a live, unprivileged connection, not a code read.** Module 01
   confirms RLS isolation by connecting through PgBouncer as the ordinary
   `univadmissions` role and demonstrating that a session with no (or a mismatched)
   `app.actor_role`/`app.actor_id` GUC sees zero rows on every RLS-protected table
   — the same class of live check that would have caught GeM's defect immediately,
   instead of a `\d+` read that only proves the policy text exists.

## Consequences

RLS in this project is defense-in-depth on top of application-level RBAC
(`require_role` FastAPI dependency), not a replacement for it — but it must be
real defense-in-depth, which requires the connecting role to actually be subject
to the policies it declares.
