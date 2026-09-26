"""payment_claim_workflow

Revision ID: 0009_payment_claim_workflow
Revises: 0008_import_batch_counts
Create Date: 2026-09-23

Module 03: payment-claim submit/confirm/reject endpoints. This migration
adds what those endpoints and the total_paid rollup need that did not
already exist from Modules 01/02:

1. `payment_claim.payment_mode` / `payment_claim.reference_number` --
   the module prompt is explicit that submit "accepts a finance_record id,
   amount, payment mode, and reference number." Neither column existed;
   `payment_mode` is a native enum (`payment_mode`:
   CASH/CHEQUE/BANK_TRANSFER/UPI/CARD/OTHER -- a closed, small vocabulary,
   matching this project's existing precedent of native enums over free
   text for closed-vocabulary fields, e.g. `application_status`). `
   reference_number` is a plain nullable string (a cash payment
   legitimately has no reference number; a bank transfer or UPI payment
   does).

2. **`finance_record` gets an `UPDATE` policy -- it did not have one at
   all.** Migration `0007_finance_record_auto_create` split
   `finance_record`'s original single `role_visibility` policy into
   `finance_record_select` (`FOR SELECT`) and `finance_record_insert`
   (`FOR INSERT`), covering exactly the two operations that migration's
   own trigger needed. Neither policy is `FOR UPDATE` or unqualified (a
   plain `CREATE POLICY` with no `FOR` clause applies to all commands),
   so with `FORCE ROW LEVEL SECURITY` still in effect, **no role --
   including `SUPER_ADMIN` -- can UPDATE any `finance_record` row at
   all**: the default when a command has no matching policy is deny, not
   allow. This module's own total_paid rollup trigger
   (`payment_claim_increment_finance_record_total_paid()`, below) needs
   exactly an `UPDATE finance_record SET total_paid = ...`. Confirmed live
   before writing the trigger, not assumed: a direct
   `UPDATE finance_record SET total_paid = 100 WHERE id = ...`, connected
   as the ordinary `sirius` role with `app.actor_role =
   'FINANCE_STAFF'` set, affected zero rows against the pre-this-migration
   schema -- the exact same "trigger's own write gets blocked by a policy
   that was never about the trigger" bug class Module 01 (`audit_log`) and
   Module 02 (`finance_record`'s own INSERT side) already hit twice.

   **Unlike migration 0007's `finance_record_insert` (`WITH CHECK (true)`,
   unconditional), this new `finance_record_update` policy reuses the
   existing finance-role allowlist instead of being unconditional --
   per this module's own scope ("RLS for both endpoints should reuse the
   existing finance_record/payment_claim policies ... rather than
   introducing new roles or GUCs").** The two cases are not analogous:
   migration 0007's INSERT-triggering actor can be *any* role (an
   `ADMISSIONS_COUNSELOR` transitioning their own applicant to
   `ADMISSION_TAKEN` fires that INSERT), so that policy had to be
   unconditional or every non-finance role's legitimate status transition
   would fail RLS. This migration's UPDATE-triggering actor is always
   whoever called `POST /finance/payment-claims/{id}/confirm` -- and that
   endpoint is application-RBAC-restricted to `FINANCE_MANAGER`/
   `SUPER_ADMIN` only, both already members of `finance_record_select`'s
   own role allowlist. Reusing that same allowlist for
   `finance_record_update` is therefore both correct (the confirming
   actor's role is always already permitted) and tighter than an
   unconditional policy would be (real defense-in-depth: a hypothetical
   future code path that reached this UPDATE from a non-finance role
   would still be denied by the database, not merely by the application
   layer's own RBAC check).

3. `applicant_create_finance_record()` (migration 0007) is unaffected by
   this: it only ever INSERTs, never UPDATEs, `finance_record`.

4. **`payment_claim_increment_finance_record_total_paid()`** fires `AFTER
   UPDATE OF status ON payment_claim WHEN (NEW.status = 'CONFIRMED' AND
   OLD.status IS DISTINCT FROM NEW.status)` and adds `NEW.amount` onto the
   parent `finance_record.total_paid` -- the rollup belongs in the
   database via trigger, the same way `finance_record` auto-creation
   (migration 0007) and the admission-gate rule (migration 0002) already
   do, not in application code, per this project's ADR-07 stance that a
   guarantee living only in a service-layer call is one omitted call path
   away from being wrong. The `WHEN` clause's `OLD.status IS DISTINCT FROM
   NEW.status` guard matters for the same reason it did in migration
   0007's trigger: `payment_claim.status` can only ever move `PENDING ->
   CONFIRMED` once in this module's workflow (there is no path back to
   `PENDING` from `CONFIRMED`), but the trigger does not assume that
   invariant holds forever -- a hypothetical future `UPDATE ... SET status
   = 'CONFIRMED'` re-run against an already-`CONFIRMED` row (no actual
   status change) must not double-count the rollup.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_payment_claim_workflow"
down_revision: str | None = "0008_import_batch_counts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAYMENT_MODE_VALUES = ["CASH", "CHEQUE", "BANK_TRANSFER", "UPI", "CARD", "OTHER"]

# Same allowlist as finance_record_select / finance_record's original
# role_visibility policy (module 01/02) -- reused here rather than
# introduced fresh, per this module's own scope.
_FINANCE_ROLE_PREDICATE = (
    "NULLIF(current_setting('app.actor_role', true), '') IN "
    "('SUPER_ADMIN', 'FINANCE_STAFF', 'FINANCE_MANAGER', 'AUDITOR')"
)

ROLLUP_FUNCTION = """
CREATE OR REPLACE FUNCTION payment_claim_increment_finance_record_total_paid() RETURNS trigger AS $$
BEGIN
    UPDATE finance_record
    SET total_paid = total_paid + NEW.amount
    WHERE id = NEW.finance_record_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    payment_mode_enum = postgresql.ENUM(*PAYMENT_MODE_VALUES, name="payment_mode")
    payment_mode_enum.create(op.get_bind(), checkfirst=True)

    op.execute(
        "ALTER TABLE payment_claim ADD COLUMN payment_mode payment_mode NOT NULL DEFAULT 'OTHER'"
    )
    op.execute("ALTER TABLE payment_claim ALTER COLUMN payment_mode DROP DEFAULT")
    op.execute("ALTER TABLE payment_claim ADD COLUMN reference_number VARCHAR")

    # Fix: finance_record never had an UPDATE policy (see module docstring
    # point 2) -- add it before creating the rollup trigger that depends on
    # UPDATE actually being permitted. Reuses the existing finance-role
    # allowlist (same as finance_record_select), not an unconditional
    # WITH CHECK (true) -- the confirming actor is always application-RBAC-
    # restricted to FINANCE_MANAGER/SUPER_ADMIN already, both members of
    # this allowlist.
    op.execute(
        f"""
        CREATE POLICY finance_record_update ON finance_record
        FOR UPDATE
        USING ({_FINANCE_ROLE_PREDICATE})
        WITH CHECK ({_FINANCE_ROLE_PREDICATE})
        """
    )

    op.execute(ROLLUP_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER payment_claim_confirmed_increments_total_paid
        AFTER UPDATE OF status ON payment_claim
        FOR EACH ROW
        WHEN (NEW.status = 'CONFIRMED' AND OLD.status IS DISTINCT FROM NEW.status)
        EXECUTE FUNCTION payment_claim_increment_finance_record_total_paid()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS payment_claim_confirmed_increments_total_paid ON payment_claim"
    )
    op.execute("DROP FUNCTION IF EXISTS payment_claim_increment_finance_record_total_paid()")
    op.execute("DROP POLICY IF EXISTS finance_record_update ON finance_record")

    op.execute("ALTER TABLE payment_claim DROP COLUMN reference_number")
    op.execute("ALTER TABLE payment_claim DROP COLUMN payment_mode")

    payment_mode_enum = postgresql.ENUM(*PAYMENT_MODE_VALUES, name="payment_mode")
    payment_mode_enum.drop(op.get_bind(), checkfirst=True)
