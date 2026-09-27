"""payment_claim_positive_amount

Revision ID: 0013_positive_amount
Revises: 0012_push_subscription
Create Date: 2026-09-27

Module 21 edge-case audit finding, fixed here: `payment_claim.amount`
had no database-level bound at all -- `POST /finance/payment-claims`
accepted a real `0.00` and a real negative amount (confirmed live:
`-50000.00`), and confirming the negative claim (an ordinary
`FINANCE_MANAGER` maker-checker action, not a special bypass) silently
*decreased* `finance_record.total_paid` via the existing
`payment_claim_confirmed_increments_total_paid()` trigger (migration
0009) -- a genuine, confirmed data-corruption path, not a theoretical
one. `api/app/schemas/payment_claim.py`'s own `PaymentClaimSubmitRequest`
now rejects `amount <= 0` at the application layer (`Field(gt=0)`,
see that schema's own docstring for the full account of the live
corruption this closes); this migration adds the matching database-
level `CHECK` constraint as the defense-in-depth backstop, the exact
same "an application-layer check alone is one omitted call path away
from being wrong" reasoning this project's own ADR-07 already applies
to `ck_payment_claim_distinct_submitter_confirmer` (migration 0002) --
reused here, not reinvented. A hypothetical future write path that
bypasses the Pydantic schema (a raw `INSERT`, a different endpoint, a
data-migration script) is still stopped by the database itself, not
merely by this one schema's own validator.

`amount > 0` (strictly, matching the schema's own `gt=0`, not `>= 0`):
a `0.00` claim is not a real transaction either -- see the schema's own
docstring for why `0.00` is rejected on the same footing as a negative
value, not treated as a permissible edge case.

**Revision id kept short (`0013_positive_amount`, not the fuller
`0013_payment_claim_positive_amount`) -- a real defect this migration's
own first attempt hit live, not merely a style choice.**
`alembic_version.version_num` is `character varying(32)` (Alembic's own
default column width, unchanged since migration `0001_baseline`); the
longer id was 34 characters and made the migration's own final
`UPDATE alembic_version SET version_num = ...` step raise a genuine
`StringDataRightTruncationError`, rolling the entire transaction back
(confirmed live: `alembic_version` and this table's own constraints
were both still at their pre-migration state afterward, exactly as
"assume transactional DDL" promises) rather than silently truncating
or partially applying. Fixed by shortening the id to fit the existing
32-character budget, not by widening the column -- every prior
revision id in this project already fits comfortably under it, and
changing a shared, cross-migration-referenced column's width is a
larger, riskier change than picking a shorter name for one migration.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_positive_amount"
down_revision: str | None = "0012_push_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE payment_claim "
        "ADD CONSTRAINT ck_payment_claim_amount_positive CHECK (amount > 0)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE payment_claim DROP CONSTRAINT IF EXISTS ck_payment_claim_amount_positive"
    )
