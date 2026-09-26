# ADR-03: Role-based RLS predicates, not a tenancy axis

## Status

Accepted

## Context

GeM's RLS design (the precedent this stack borrows ADR-01's pooling
discipline from) scopes every policy to a single `entity_id` GUC, because
GeM is multi-tenant across two real operating entities. Sirius has
no equivalent tenancy axis -- Illinois Tech Mumbai is a single institution.
Row-level security here exists to encode role-based visibility (a counselor
sees their own assigned applicants; finance data is invisible to admissions
roles and vice versa) as defense-in-depth under the application-level RBAC
dependency (`require_role`, `app.core.deps`), not to separate tenants.

## Decision

Every RLS-protected table's policy reads two GUCs, both set via `SET LOCAL`
inside `open_scoped_session` (ADR-01): `app.actor_id` (the requesting user's
id) and `app.actor_role` (their role code, e.g. `ADMISSIONS_COUNSELOR`).
`NULLIF(current_setting(name, true), '')` wraps every read, per ADR-01.

- **`applicant` / `application_status_event`**: an `ADMISSIONS_COUNSELOR`
  sees only applicants where `assigned_counselor_id = app.actor_id`; every
  other role (`SUPER_ADMIN`, `ADMISSIONS_MANAGER`, `FINANCE_STAFF`,
  `FINANCE_MANAGER`, `AUDITOR`) sees every applicant. Finance roles need
  full applicant visibility to reconcile which applicant a payment belongs
  to; an auditor needs full visibility by definition.
- **`finance_record` / `payment_claim`**: visible only to `FINANCE_STAFF`,
  `FINANCE_MANAGER`, `SUPER_ADMIN`, `AUDITOR` -- an admissions counselor or
  manager has no legitimate reason to see fee balances or payment claims,
  and RLS enforces that even if a future route forgets to check the role
  itself.
- **`import_batch`**: visible to `ADMISSIONS_MANAGER`, `SUPER_ADMIN`,
  `AUDITOR` -- the roles who need to know when/how applicant data entered
  the system.
- **`audit_log`**: visible only to `SUPER_ADMIN` and `AUDITOR` -- the two
  roles whose job includes reviewing the record of every change.
- **`role`, `user`, `user_backup_code`**: **not** RLS-scoped, the same
  identity-axis exception GeM's ADR-08 establishes. Login must look up a
  user by email before any session (and therefore any `app.actor_role`)
  exists, which makes an RLS-scoped `user` table structurally impossible to
  authenticate against. `role` is a fixed six-row catalogue, not
  per-actor data. `user_backup_code` is scoped implicitly by the service
  layer (a user only ever verifies their own session's backup codes) rather
  than by RLS, for the same structural reason.

Every policy uses `FORCE ROW LEVEL SECURITY` (ADR-02) and applies to both
`USING` (reads) and `WITH CHECK` (writes) -- a counselor cannot read another
counselor's applicant, and cannot silently reassign an applicant to
themselves and write a row that violates the same visibility rule.

## Consequences

This is coarser than a full per-action RBAC matrix (module scope explicitly
defers status-transition and payment-workflow endpoints to the next
module), but it is real, live-verified isolation for the tables this module
creates, not a placeholder. Verification: connect as the ordinary
`sirius` role (never superuser, per ADR-02) with different
`app.actor_role`/`app.actor_id` GUC combinations and confirm each role sees
exactly its permitted rows.
