# ADR-01: PgBouncer transaction pooling constrains the RLS implementation

## Status

Accepted

## Context

PgBouncer runs in transaction pooling mode, which returns the server connection to
the pool at the end of every transaction. Row-level security scoping depends on
session GUCs (`app.actor_id`, `app.actor_role`, `app.client_ip`).

## Decision

Three consequences, all mandatory, carried over unchanged from the GeM precedent
this project's stack is modeled on:

1. **`SET LOCAL`, never `SET`.** A plain `SET` binds to the server session, which
   is handed to a different client on the next transaction — the GUC either
   vanishes or, far worse, leaks one actor's identity into another request. Every
   request opens a transaction, issues `SET LOCAL` for every RLS GUC it needs,
   does its work, commits. A request that touches the database outside a
   transaction is a defect.
2. **Disable asyncpg's prepared-statement cache.** Pass
   `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}`
   and set `?prepared_statement_cache_size=0` on the DSN. Without this the driver
   caches statements against a server connection it will not get back, producing
   intermittent `prepared statement "__asyncpg_stmt_x__" does not exist` errors
   under load — invisible in local single-connection testing.
3. **Alembic connects direct to Postgres, bypassing PgBouncer entirely.** DDL and
   migration advisory locks need session continuity that transaction pooling does
   not provide.

**`NULLIF` around every `current_setting()` call.** `current_setting(name, true)`
returns NULL the first time a custom GUC is queried on a given pooled backend, but
once `SET LOCAL` has been issued at least once on that backend, Postgres creates a
persistent placeholder whose reset value is an **empty string**, not NULL, once the
owning transaction ends. The next client PgBouncer hands that backend to, if it
forgets to set the GUC, sees `current_setting(..., true)` return `''`. Every policy
predicate and trigger function in this project wraps the call as
`NULLIF(current_setting(name, true), '')::uuid` (or the appropriate type) so both
the never-set case (NULL) and the reset-after-previous-use case (`''`) normalize to
NULL, and the comparison fails closed — zero rows, not a cast exception — in both
cases.

## Consequences

**Alternatives rejected.** Session pooling — gives back plain `SET` but destroys
the connection multiplexing PgBouncer exists for. Application-level scoping
without RLS — moves the access guarantee from the database to every query, where
one forgotten `WHERE` clause is a data leak. Statement pooling — breaks
transactions outright.

**Consequence to verify:** an integration check that runs two concurrent sessions
with different actor/role GUC values and confirms RLS policies see only what each
actor is permitted to see, exercised against the real Postgres/PgBouncer stack, not
mocked.
