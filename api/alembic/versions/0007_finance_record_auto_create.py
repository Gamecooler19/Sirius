"""finance_record_auto_create

Revision ID: 0007_finance_record_auto_create
Revises: 0006_status_enum_rename
Create Date: 2026-09-22

Module 01 built `finance_record_requires_admission_taken()` as a `BEFORE
INSERT` **gate**: it blocks an insert unless the applicant is already at
`ADMISSION_TAKEN`, but it does not itself create anything. The status-
transition endpoint this module adds needs `finance_record` to come into
existence automatically the moment an applicant's status transitions *to*
`ADMISSION_TAKEN`, with zero application code beyond the status `UPDATE`
itself -- the module prompt is explicit: "relies on the existing database
trigger to create the finance_record automatically ... rather than doing
that in application code." That automatic-creation trigger did not
previously exist; this migration adds it.

`applicant_create_finance_record()` fires `AFTER UPDATE OF current_status
ON applicant`, `WHEN (NEW.current_status = 'ADMISSION_TAKEN' AND
OLD.current_status IS DISTINCT FROM NEW.current_status)` -- only on an
actual transition *into* `ADMISSION_TAKEN`, not on every update to a row
that happens to already be there. A nested `BEGIN ... EXCEPTION WHEN
unique_violation THEN NULL` block makes it idempotent against
`finance_record`'s own `uq_finance_record_applicant` constraint, so a
hypothetical second transition into `ADMISSION_TAKEN` (there is no path
back out of it in this module's transition table, but the trigger does
not assume that invariant holds forever) never raises a duplicate-key
error out of the trigger.

**Why a plain `INSERT` wrapped in an exception handler, not `INSERT ...
ON CONFLICT (applicant_id) DO NOTHING`.** This is not a style preference --
the `ON CONFLICT` form was tried first and failed differently against the
live stack than the RLS-split fix below addresses, for a subtler reason
confirmed against Postgres's own documentation (`CREATE POLICY`): "If an
INSERT has ... an ON CONFLICT DO NOTHING clause with an arbiter index or
constraint specification, then SELECT permissions are required on the
relation, and the rows proposed for insertion are checked using the
relation's SELECT policies." `finance_record_select` restricts SELECT to
`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR` -- so even after
splitting the INSERT policy to `WITH CHECK (true)` (below), an
`ADMISSIONS_COUNSELOR`-driven transition still failed with `new row
violates row-level security policy for table "finance_record"`, because
`ON CONFLICT (applicant_id) DO NOTHING` implicitly needs the SELECT policy
too, for the conflict check itself, and a counselor has none. Confirmed by
running exactly this failure against the live stack (see the module-02
report) before landing this fix: a plain `INSERT` (no `ON CONFLICT`
clause) does not trigger this SELECT-policy requirement at all, and
catching `unique_violation` in a nested block gives the identical
idempotency guarantee without it.

**Why `finance_record`'s RLS policy must still be split (the same fix
`audit_log` needed in migration 0003, for a related but distinct reason).**
This trigger fires regardless of which role performed the status
`UPDATE` -- an `ADMISSIONS_COUNSELOR` transitioning their own applicant to
`ADMISSION_TAKEN` causes the trigger to insert into `finance_record` on
their behalf. `finance_record`'s single `role_visibility` policy (module
01) restricts both `USING` and `WITH CHECK` to
`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR` -- an
`ADMISSIONS_COUNSELOR`-driven insert would fail RLS's `WITH CHECK`, for
the identical reason `audit_log`'s original single policy did: the check
was never actually about the trigger. Split into `finance_record_select`
(`FOR SELECT`, the original role allowlist, unchanged) and
`finance_record_insert` (`FOR INSERT`, `WITH CHECK (true)`) -- reads stay
restricted to the finance roles; the trigger's insert, the only way
`finance_record` is ever created (application code never inserts into it
directly), is never blocked by a role check that was never about the
trigger. This split alone was not sufficient on its own, though -- see the
`ON CONFLICT` note above for the second, independent fix this required.

**`WITH CHECK (true)` on `finance_record_insert` applies to INSERT only
and does not touch `finance_record_select`'s own `USING` clause --
stated explicitly because the two policies are separate Postgres objects
with separate, unrelated predicates, not one relaxed rule.** An
`ADMISSIONS_COUNSELOR` can now cause a row to be inserted (via the
trigger) but still cannot read any `finance_record` row afterward,
including the one their own transition just created. Verified live, not
by re-reading this policy SQL: a real `ADMISSIONS_COUNSELOR` session
(via `app.core.db.open_scoped_session` with that role's real
`actor_id`/`actor_role`, the identical mechanism a real request uses)
transitioned its own assigned applicant to `ADMISSION_TAKEN` through the
actual `POST /applicants/{id}/status` endpoint, then immediately queried
`finance_record` for that applicant in a fresh scoped session under the
same counselor identity and saw zero rows -- while a superuser connection
confirmed the row genuinely exists, and a `FINANCE_MANAGER`-scoped session
saw it correctly. See `reports/module-02-status-and-import.md`'s
"Follow-up verification" section for the full account.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_finance_record_auto_create"
down_revision: str | None = "0006_status_enum_rename"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTO_CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION applicant_create_finance_record() RETURNS trigger AS $$
BEGIN
    BEGIN
        INSERT INTO finance_record (applicant_id, total_fee_due, total_paid)
        VALUES (NEW.id, 0, 0);
    EXCEPTION WHEN unique_violation THEN
        -- Already exists (a hypothetical re-entry into ADMISSION_TAKEN) --
        -- not an error. A plain INSERT + catch, not ON CONFLICT DO NOTHING:
        -- see this migration's module docstring for why ON CONFLICT's
        -- implicit SELECT-policy requirement broke this for any role
        -- without finance_record SELECT access (every role except
        -- SUPER_ADMIN/FINANCE_STAFF/FINANCE_MANAGER/AUDITOR).
        NULL;
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(AUTO_CREATE_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER applicant_create_finance_record_on_admission_taken
        AFTER UPDATE OF current_status ON applicant
        FOR EACH ROW
        WHEN (NEW.current_status = 'ADMISSION_TAKEN' AND OLD.current_status IS DISTINCT FROM NEW.current_status)
        EXECUTE FUNCTION applicant_create_finance_record()
        """
    )

    op.execute("DROP POLICY IF EXISTS role_visibility ON finance_record")
    op.execute(
        """
        CREATE POLICY finance_record_select ON finance_record
        FOR SELECT
        USING (NULLIF(current_setting('app.actor_role', true), '') IN
               ('SUPER_ADMIN', 'FINANCE_STAFF', 'FINANCE_MANAGER', 'AUDITOR'))
        """
    )
    op.execute(
        """
        CREATE POLICY finance_record_insert ON finance_record
        FOR INSERT
        WITH CHECK (true)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS finance_record_insert ON finance_record")
    op.execute("DROP POLICY IF EXISTS finance_record_select ON finance_record")
    op.execute(
        """
        CREATE POLICY role_visibility ON finance_record
        USING (NULLIF(current_setting('app.actor_role', true), '') IN
               ('SUPER_ADMIN', 'FINANCE_STAFF', 'FINANCE_MANAGER', 'AUDITOR'))
        WITH CHECK (NULLIF(current_setting('app.actor_role', true), '') IN
                    ('SUPER_ADMIN', 'FINANCE_STAFF', 'FINANCE_MANAGER', 'AUDITOR'))
        """
    )

    op.execute(
        "DROP TRIGGER IF EXISTS applicant_create_finance_record_on_admission_taken ON applicant"
    )
    op.execute("DROP FUNCTION IF EXISTS applicant_create_finance_record()")
