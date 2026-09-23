"""Pydantic response schemas for the applicant list/detail/status-history/
finance read endpoints (Module 04).

Every field here is deliberately hand-picked, not `model_config =
ConfigDict(from_attributes=True)` over the raw ORM object's `__dict__` --
this project's response models exist specifically so that an internal-only
column added to a model later (a password hash, a TOTP secret, or
anything else not meant for the wire) cannot leak by accident just because
a route forgot to re-check what it serializes. `Applicant` and its related
models have no such sensitive columns today, but the pattern is the same
one `app.schemas.payment_claim`/`app.schemas.status` already established,
applied here for consistency and to keep that guarantee ORM-model-agnostic.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ApplicationStatus, PaymentClaimStatus, PaymentMode


class ApplicantSummary(BaseModel):
    """One row of the `GET /applicants` list."""

    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    program: str
    intake_cycle: str
    current_status: ApplicationStatus
    assigned_counselor_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ApplicantListResponse(BaseModel):
    items: list[ApplicantSummary]
    total: int
    limit: int
    offset: int


class ApplicantDetail(ApplicantSummary):
    """`GET /applicants/{id}` -- same fields as the list row today, kept
    as a distinct model (rather than reusing `ApplicantSummary` directly
    as the route's response type) so the detail view can grow
    detail-only fields later without changing the list's own shape.
    """

    import_batch_id: uuid.UUID | None


class StatusHistoryEvent(BaseModel):
    id: uuid.UUID
    applicant_id: uuid.UUID
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    changed_by: uuid.UUID | None
    note: str | None
    created_at: datetime


class StatusHistoryResponse(BaseModel):
    items: list[StatusHistoryEvent]


class PaymentClaimDetail(BaseModel):
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
    created_at: datetime


class ApplicantFinanceResponse(BaseModel):
    finance_record_id: uuid.UUID
    applicant_id: uuid.UUID
    total_fee_due: Decimal
    total_paid: Decimal
    payment_claims: list[PaymentClaimDetail]


class PaymentClaimListResponse(BaseModel):
    items: list[PaymentClaimDetail]
    total: int
    limit: int
    offset: int


class ImportBatchSummary(BaseModel):
    id: uuid.UUID
    source_filename: str
    status: str
    row_count: int | None
    checksum: str | None
    created_count: int
    updated_count: int
    flagged_count: int
    rejected_count: int
    error_detail: str | None
    imported_by: uuid.UUID
    created_at: datetime
    completed_at: datetime | None


class ImportBatchListResponse(BaseModel):
    items: list[ImportBatchSummary]
    total: int
    limit: int
    offset: int


class PaymentClaimStatusBreakdown(BaseModel):
    """One status bucket (`PENDING`/`CONFIRMED`/`REJECTED`) within a
    reconciliation row. Always present for all three `PaymentClaimStatus`
    values in a given row's `claims_by_status`, even when a status has
    zero claims in that scope -- `count: 0, amount: 0` rather than the
    status being absent from the list, so a caller can always index by
    status without a membership check.
    """

    status: PaymentClaimStatus
    count: int
    amount: Decimal


class ReconciliationCycle(BaseModel):
    """One `GET /finance/reconciliation` row: every `finance_record`
    whose parent `applicant.intake_cycle` equals this cycle, summed, plus
    the same breakdown for every `payment_claim` against one of those
    `finance_record`s.
    """

    intake_cycle: str
    finance_record_count: int
    total_fee_due: Decimal
    total_paid: Decimal
    outstanding: Decimal
    claims_by_status: list[PaymentClaimStatusBreakdown]


class ReconciliationTotals(BaseModel):
    """Same shape as `ReconciliationCycle` minus `intake_cycle` -- the
    sum of every cycle row combined. Built by summing the already-
    computed `cycles` array in the route itself (`app.routers.reconciliation`),
    not by a second, independent SQL aggregate query -- see that route's
    own docstring for why this is a structural guarantee against drift
    between this field and the array it summarizes, not merely a fact
    that happens to be true today.
    """

    finance_record_count: int
    total_fee_due: Decimal
    total_paid: Decimal
    outstanding: Decimal
    claims_by_status: list[PaymentClaimStatusBreakdown]


class ReconciliationResponse(BaseModel):
    cycles: list[ReconciliationCycle]
    totals: ReconciliationTotals
