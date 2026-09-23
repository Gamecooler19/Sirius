"""Request/response schemas for the payment-claim submit/confirm/reject
endpoints.

`submitted_by` is deliberately absent from `PaymentClaimSubmitRequest` --
the router takes it from the authenticated session identity, never from
the request body, per this module's own explicit requirement: trusting a
client-supplied identity for an audit-relevant field (who actually
submitted this claim) defeats the entire point of recording it.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import PaymentClaimStatus, PaymentMode


class PaymentClaimSubmitRequest(BaseModel):
    finance_record_id: uuid.UUID
    amount: Decimal
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
    confirmed_at: datetime | None
    note: str | None
