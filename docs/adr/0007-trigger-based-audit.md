# ADR-07: Trigger-based audit, not an application-level helper

## Status

Accepted

## Context

Every mutation on a business table needs an audit trail: who changed what, when,
from what value to what value, and from where. The question this ADR settles is
where that guarantee lives: as a function application code calls, or as a database
trigger that fires regardless of what code path performed the write.

## Decision

`write_audit()` is a Postgres trigger function, `AFTER INSERT OR UPDATE OR DELETE
FOR EACH ROW`, attached to every business table. It writes the table name, row id,
operation, the old and new row images as JSONB, the actor (read from
`current_setting('app.actor_id', true)`), and the real client IP (read from
`current_setting('app.client_ip', true)`) into `audit_log` — a single generic table
keyed by `table_name` + `record_id`, per the module scope, rather than one audit
table per entity.

A second trigger, `audit_log_block_mutation`, fires `BEFORE UPDATE OR DELETE` on
`audit_log` itself and unconditionally raises an exception — the audit trail is
append-only, enforced at the database, not by convention.

`audit_log` is excluded from `write_audit()`'s own trigger set, so an insert into
`audit_log` does not recurse into auditing itself.

`updated_at` maintenance also lives here as a trigger (`set_updated_at`), so it
stays correct even for a raw-SQL fix applied by hand in a console.

## Consequences

**Why a trigger and not an application-level helper function.** A helper that
every service-layer write must remember to call is a discipline, and discipline is
defeated by exactly one forgotten call. A trigger is a guarantee: it cannot be
bypassed by a code path that forgets to call it, because there is no "calling" it
— it fires on the write itself, including a raw SQL fix applied by hand in a psql
console during an incident, which is precisely the kind of write most likely to
happen without going through application code and most in need of being on the
record.

**Cost accepted.** Trigger logic is harder to unit test in isolation than a Python
function and lives outside the application's normal code review surface
(migrations, not `app/services/`). This module's verification exercises the
trigger directly against a real database rather than mocking it.

**Alternatives rejected.**
- **Application-level `write_audit()` helper, called from every service method.**
  Rejected for the reason above — one omission silently breaks the guarantee.
- **Outbox pattern / change-data-capture from WAL.** Correct for very high-volume
  systems needing async processing of change events; not justified for an
  internal admissions/finance tracker at this scale.
