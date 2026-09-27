"""Request/response schemas for the payment-claim submit/confirm/reject
endpoints.

`submitted_by` is deliberately absent from `PaymentClaimSubmitRequest` --
the router takes it from the authenticated session identity, never from
the request body, per this module's own explicit requirement: trusting a
client-supplied identity for an audit-relevant field (who actually
submitted this claim) defeats the entire point of recording it.
"""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PaymentClaimStatus, PaymentMode
from app.schemas._datetime import UtcDatetime


class PaymentClaimSubmitRequest(BaseModel):
    """**`amount` must be strictly positive (Module 21 audit finding,
    fixed here).** Before this fix, neither this schema nor any
    database constraint rejected `amount <= 0` -- confirmed live, and
    confirmed to be a genuinely severe defect, not merely a cosmetic
    input-validation gap: a `0.00` submission was accepted with a real
    `200`, and a real `-50000.00` submission was not only accepted but,
    once confirmed by a `FINANCE_MANAGER` (a real, ordinary maker-
    checker action, not a special bypass), the existing
    `payment_claim_confirmed_increments_total_paid()` trigger (migration
    0009) added that negative amount to `finance_record.total_paid`
    exactly as it adds any other confirmed claim's amount -- silently
    **decreasing** a real applicant's recorded payment total (observed
    live: a genuine `250000.00` dropped to `200000.00` from one
    confirmed negative claim) and propagating that corruption straight
    into `GET /finance/reconciliation`'s own aggregate totals, with no
    error, warning, or audit distinction from a legitimate payment
    anywhere in the chain. `gt=0` (strictly greater than zero, not
    `ge=0`) is the correct bound, not merely a defensive minimum: a
    `0.00` "payment" is not a real transaction either (nothing changed
    hands), and permitting it would still let a `0.00` claim be
    confirmed and recorded as if a real payment occurred, polluting
    `payment_claim`'s own audit trail with a claim that documents
    nothing. This is a genuinely bounded fix, not a full audit of
    every numeric field in this codebase -- see
    `reports/module-21-edge-case-audit.md`'s own input-boundaries
    section for the fields this pass deliberately left unexamined.
    """

    finance_record_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    payment_mode: PaymentMode
    reference_number: str | None = None


class PaymentClaimResolveRequest(BaseModel):
    """Shared body shape for both /confirm and /reject -- the only input
    either action takes is an optional note."""

    note: str | None = None


class PaymentClaimResponse(BaseModel):
    id: uuid.UUID
    finance_record_id: uuid.UUID
    amount: Decimal
    status: PaymentClaimStatus
    payment_mode: PaymentMode
    reference_number: str | None
    submitted_by: uuid.UUID
    confirmed_by: uuid.UUID | None
    confirmed_at: UtcDatetime | None
    note: str | None
