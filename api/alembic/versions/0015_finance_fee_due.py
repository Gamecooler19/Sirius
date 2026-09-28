"""finance_fee_due

Revision ID: 0015_finance_fee_due
Revises: 0014_applicant_field_length
Create Date: 2026-09-28

Module 22 Part 2: `total_fee_due` was never written by any real API
endpoint -- confirmed live via the full `audit_log` history for
`finance_record` before this migration: every single row's own
`total_fee_due` was `0.00` from the moment
`applicant_create_finance_record()` (migration 0007) inserted it, and
stayed `0.00` forever after; only `total_paid` ever changed, via the
payment-confirm rollup trigger (migration 0009). Every dashboard/
reconciliation "outstanding" figure derived from `total_fee_due -
total_paid` was therefore wrong for every applicant with any confirmed
payment at all -- confirmed live: two real `finance_record` rows show
a genuine `-250000.00`/`-300000.00` "outstanding" balance today, a
real applicant who has paid money against a fee that was never
actually entered anywhere, not a hypothetical edge case.

**1. `total_fee_due` becomes nullable, default changes from `0` to
`NULL` -- this is the real fix for the "fee not set" vs "fee = 0"
distinction the module's own scope requires, not a cosmetic
schema tweak.** `0` cannot represent "not yet decided" and "confirmed
to be free" as two different facts at the same time -- confirmed live
this ambiguity is not merely theoretical: both of this database's own
pre-existing rows are `0.00` today, and that `0.00` means "nobody has
told the system what this applicant owes yet," never "this applicant's
tuition is genuinely free." A dashboard/reconciliation aggregate that
cannot tell those two cases apart will silently under-report
outstanding balances for every applicant whose fee was simply never
entered, exactly the corruption already observed. `NULL` is the only
value that structurally cannot be confused with a real, decided `0`
figure -- the same reasoning this project's own `payment_claim.amount`
`gt=0` bound (migration 0013) already applied to a different but
related ambiguity ("0.00 is not a real transaction either").

Both pre-existing `0.00` rows are backfilled to `NULL` as part of this
migration -- confirmed via `write_audit()`'s own historical rows (see
above) that neither ever received a real, application-driven write;
their `0.00` is exactly the auto-create trigger's own placeholder
default, not a finance manager's actual decision that the fee is zero.
Backfilling a placeholder default to the value that now represents
"never decided" is the correct one-time migration, not data loss --
if either applicant's fee genuinely is zero, a `FINANCE_MANAGER` can
now say so explicitly through the real `PATCH
/finance-records/{id}/fee-due` endpoint this module adds, and that
explicit `0` will be structurally distinguishable from an unset fee
from that point on.

`applicant_create_finance_record()` (migration 0007) is updated in
place to insert `NULL` for `total_fee_due` instead of `0` -- every
newly-created `finance_record` going forward starts in the correct
"fee not set" state.

**2. `CHECK` constraints, added only after confirming zero existing
violations (same "verify before adding" precedent
`0013_positive_amount`/`0014_applicant_field_length` already
established):**

- `ck_finance_record_fee_due_nonnegative`: `total_fee_due IS NULL OR
  total_fee_due >= 0` -- `NULL` (not set) is always permitted; a real,
  decided fee must be non-negative. `>= 0`, not `> 0`, unlike
  `payment_claim.amount`'s own `> 0` bound: a genuinely free program
  (fee due `0.00`) is a real, meaningful business fact a
  `FINANCE_MANAGER` may legitimately record, unlike a `0.00` payment
  claim (migration 0013's own reasoning, "nothing changed hands"), so
  the two fields' bounds are deliberately different, not a copy-paste
  of one onto the other.
- `ck_finance_record_total_paid_nonnegative`: `total_paid >= 0`.
  `total_paid` itself already could not go negative through any real
  write path today (`payment_claim.amount`'s own `> 0` bound plus its
  `CHECK` constraint, migration 0013, already prevents a confirmed
  claim from ever subtracting from the rollup) -- this constraint is
  pure defense-in-depth for a hypothetical future write path, the
  identical "one omitted call path away from being wrong" reasoning
  ADR-07 already applies throughout this project, not a fix for an
  observed live violation (confirmed zero rows violate it before this
  migration runs).

Verified live, immediately before writing this migration: `SELECT
count(*) FROM finance_record WHERE total_fee_due < 0 OR total_paid <
0` returned `0`.

**A real defect this migration's own first run hit live, not merely
hypothesized: the backfill `UPDATE` above silently affected zero
rows.** Alembic's own connection runs as `sirius`, the table-owning
role, and `finance_record` carries `FORCE ROW LEVEL SECURITY` (ADR-02)
-- so even the owning role is subject to the table's own RLS policies,
not exempt from them. A migration has no request-scoped `app.actor_id`/
`app.actor_role` GUC set at all (the same fact `0010_password_reset_
token`'s own docstring already notes for a different endpoint), so
`finance_record_update`'s policy predicate,
`NULLIF(current_setting('app.actor_role', true), '') IN (...)`,
evaluated to `NULL` (neither `true` nor `false`) for this `UPDATE` --
and Postgres's own RLS semantics silently exclude every row a policy's
`USING` clause does not affirmatively match, with no error and no
warning, exactly like an ordinary `WHERE` clause that matches nothing.
Confirmed live: the backfill ran with `UPDATE 0` reported, and both
pre-existing rows were still `0.00`, not `NULL`, immediately
afterward. Fixed by wrapping the backfill in a local
`SET LOCAL app.actor_role = 'SUPER_ADMIN'` (scoped to this migration's
own transaction only, per `SET LOCAL`'s own documented behavior --
never a session-wide or permanent change) immediately before the
`UPDATE`, giving it the identical GUC a real `SUPER_ADMIN`-authenticated
request would carry and satisfying the very policy this migration
itself is about to narrow.

**A second real ordering defect, also hit live on the first corrected
run: `DROP NOT NULL` must run *before* the backfill, not after.** The
column is still `NOT NULL` at the moment the backfill `UPDATE` runs if
that `UPDATE` is issued first (the naive, "logical" order: fix the
data, then relax the constraint) -- a real
`asyncpg.exceptions.NotNullViolationError` was raised live attempting
exactly that ordering, correctly rejected by the database rather than
silently accepted. `upgrade()` below issues `ALTER TABLE ... DROP NOT
NULL` first, then the backfill `UPDATE` against the now-nullable
column.

**3. `finance_record_update`'s RLS policy (migration 0009) is
tightened from the current finance-role allowlist (`SUPER_ADMIN`,
`FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR`) down to `SUPER_ADMIN`/
`FINANCE_MANAGER` only -- the module's own explicit requirement, and a
real, not merely theoretical, over-grant.** `FINANCE_STAFF` may submit
a payment claim but, per this project's own established maker-checker
separation (`app.routers.payment_claim`'s own docstring:
"`FINANCE_STAFF` may submit but never resolve any claim"), was never
supposed to directly mutate a `finance_record` row at all -- the
original migration 0009 policy was scoped to "every role that can see
finance_record" rather than "every role that is actually supposed to
write to it," a broader grant than the application-layer RBAC this
project otherwise already enforces at every write endpoint.
`AUDITOR`'s presence is a more clear-cut case: an auditor reviews
records, an auditor updating the very figures they are meant to
independently verify defeats the point of the role. Both application
code paths that ever `UPDATE finance_record` (this module's new
fee-due endpoint, and the existing payment-confirm rollup trigger) are
already restricted at the application RBAC layer to
`FINANCE_MANAGER`/`SUPER_ADMIN`. **The rollup trigger's own `UPDATE`
is not exempt from this RLS narrowing** -- `payment_claim_increment_
finance_record_total_paid()` (migration 0009) is a plain `plpgsql`
function, not `SECURITY DEFINER`, so it executes under the same
connection role and the same `app.actor_role` GUC as whichever request
caused it to fire, exactly like any other statement in that
transaction; it is not exempt from RLS the way `write_audit()`'s
`INSERT` into `audit_log` needed an unconditional policy to be exempt
(migration 0003). This is fine specifically *because* the only caller
that can ever reach it -- `POST /finance/payment-claims/{id}/confirm`
-- is already application-RBAC-restricted to `FINANCE_MANAGER`/
`SUPER_ADMIN`, both still members of the new, narrower policy; verified
live after this migration, not merely reasoned about (see the
module-22 report's own Part 2 section for the real confirm call that
proves the rollup still fires correctly under the new policy).
Narrowing the RLS policy to match application RBAC is the identical
defense-in-depth this project's ADR-07 already applies everywhere
else -- the database no longer trusts an application-layer role check
alone to keep `FINANCE_STAFF`/`AUDITOR` from directly mutating a real
financial figure.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_finance_fee_due"
down_revision: str | None = "0014_applicant_field_length"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_FINANCE_ROLE_PREDICATE = (
    "NULLIF(current_setting('app.actor_role', true), '') IN "
    "('SUPER_ADMIN', 'FINANCE_STAFF', 'FINANCE_MANAGER', 'AUDITOR')"
)
_NEW_FINANCE_MANAGER_PREDICATE = (
    "NULLIF(current_setting('app.actor_role', true), '') IN "
    "('SUPER_ADMIN', 'FINANCE_MANAGER')"
)

AUTO_CREATE_FUNCTION_NULL_FEE = """
CREATE OR REPLACE FUNCTION applicant_create_finance_record() RETURNS trigger AS $$
BEGIN
    BEGIN
        INSERT INTO finance_record (applicant_id, total_fee_due, total_paid)
        VALUES (NEW.id, NULL, 0);
    EXCEPTION WHEN unique_violation THEN
        -- Already exists (a hypothetical re-entry into ADMISSION_TAKEN) --
        -- not an error. See migration 0007's own docstring for why a
        -- plain INSERT + catch, not ON CONFLICT DO NOTHING, is required
        -- here.
        NULL;
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

AUTO_CREATE_FUNCTION_ZERO_FEE = """
CREATE OR REPLACE FUNCTION applicant_create_finance_record() RETURNS trigger AS $$
BEGIN
    BEGIN
        INSERT INTO finance_record (applicant_id, total_fee_due, total_paid)
        VALUES (NEW.id, 0, 0);
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # DROP NOT NULL first, then backfill -- the reverse order (backfill
    # while still NOT NULL) is impossible by construction: a real
    # attempt to do it that way was tried first and correctly rejected
    # live with a genuine NotNullViolationError, confirming the column
    # itself, not merely RLS, would otherwise block this UPDATE.
    op.execute("ALTER TABLE finance_record ALTER COLUMN total_fee_due DROP NOT NULL")

    # Backfill: every existing 0.00 row is the auto-create trigger's own
    # placeholder, never a real application-driven write (confirmed via
    # write_audit()'s own history -- see module docstring), so it
    # becomes NULL ("not set"), not a data loss.
    #
    # SET LOCAL app.actor_role -- required, not defensive: without it
    # this UPDATE silently affects zero rows under the still-in-effect
    # (pre-narrowing) finance_record_update RLS policy, since a
    # migration carries no request-scoped app.actor_role GUC at all.
    # See module docstring for the live failure this fixes. Scoped to
    # this transaction only (SET LOCAL, not SET) -- never leaks into any
    # later statement or connection.
    op.execute("SET LOCAL app.actor_role = 'SUPER_ADMIN'")
    op.execute("UPDATE finance_record SET total_fee_due = NULL WHERE total_fee_due = 0")

    op.execute(
        "ALTER TABLE finance_record ADD CONSTRAINT ck_finance_record_fee_due_nonnegative "
        "CHECK (total_fee_due IS NULL OR total_fee_due >= 0)"
    )
    op.execute(
        "ALTER TABLE finance_record ADD CONSTRAINT ck_finance_record_total_paid_nonnegative "
        "CHECK (total_paid >= 0)"
    )

    op.execute(AUTO_CREATE_FUNCTION_NULL_FEE)

    op.execute("DROP POLICY IF EXISTS finance_record_update ON finance_record")
    op.execute(
        f"""
        CREATE POLICY finance_record_update ON finance_record
        FOR UPDATE
        USING ({_NEW_FINANCE_MANAGER_PREDICATE})
        WITH CHECK ({_NEW_FINANCE_MANAGER_PREDICATE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS finance_record_update ON finance_record")
    op.execute(
        f"""
        CREATE POLICY finance_record_update ON finance_record
        FOR UPDATE
        USING ({_OLD_FINANCE_ROLE_PREDICATE})
        WITH CHECK ({_OLD_FINANCE_ROLE_PREDICATE})
        """
    )

    op.execute(AUTO_CREATE_FUNCTION_ZERO_FEE)

    op.execute(
        "ALTER TABLE finance_record DROP CONSTRAINT IF EXISTS ck_finance_record_total_paid_nonnegative"
    )
    op.execute(
        "ALTER TABLE finance_record DROP CONSTRAINT IF EXISTS ck_finance_record_fee_due_nonnegative"
    )

    op.execute("SET LOCAL app.actor_role = 'SUPER_ADMIN'")
    op.execute("UPDATE finance_record SET total_fee_due = 0 WHERE total_fee_due IS NULL")
    op.execute("ALTER TABLE finance_record ALTER COLUMN total_fee_due SET NOT NULL")
