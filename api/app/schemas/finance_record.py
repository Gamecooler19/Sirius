"""Request/response schema for `PATCH /finance-records/{id}/fee-due`
(Module 22 Part 2).

`total_fee_due` is `None` in the response when unset ("fee not set"),
distinct from a real, decided `Decimal("0.00")` -- see
`app.models.finance_record`'s own docstring for the full account of
why this distinction is a real fix, not a schema nicety.
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class FinanceRecordFeeDueUpdateRequest(BaseModel):
    """**`ge=0, max_digits=12, decimal_places=2`** -- matches
    `finance_record.total_fee_due`'s own real column type,
    `numeric(12,2)`, exactly, and reuses the identical bound-choice
    reasoning `app.schemas.payment_claim.PaymentClaimSubmitRequest`
    already established for `amount` (Module 21 follow-up): without a
    `max_digits`/`decimal_places` bound, an oversized or over-precise
    value would either silently round (a fee the caller did not
    actually type) or overflow the database's own column at write
    time, producing an unhandled `500` instead of a clean `422`.
    `ge=0` (not `gt=0`, unlike `PaymentClaimSubmitRequest.amount`) --
    a genuinely free program is a real, meaningful `0.00` fee a
    `FINANCE_MANAGER` may legitimately record; see the migration's own
    docstring for why this field's bound is deliberately different
    from `payment_claim.amount`'s `gt=0`. There is no way to submit
    `None`/"unset" through this endpoint by design: unsetting a fee
    that was previously entered is not a real workflow this module's
    own scope describes, and every `finance_record` already starts
    unset by default (migration 0015) -- this endpoint only ever moves
    a record from "unset" to "a real decided value," or updates an
    already-decided value to a new one.
    """

    total_fee_due: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
