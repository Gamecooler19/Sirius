"""PaymentClaim: a submitted payment awaiting confirmation, with a
maker-checker separation between the person who submitted it
(`submitted_by`) and the person who confirmed it (`confirmed_by`). The two
must never resolve to the same user for a given claim -- self-confirmation
would defeat the entire point of a two-person control on money movement.

Enforced twice, deliberately redundant:
1. A `CHECK (confirmed_by IS NULL OR confirmed_by <> submitted_by)`
   constraint at the database, so no code path -- including a raw SQL
   `UPDATE` run by hand -- can ever write a same-user confirmation, matching
   this project's general preference for database-enforced invariants over
   ones that live only in service code (ADR-07's reasoning applies equally
   here, even though this is a CHECK constraint rather than a trigger).
2. The service-layer confirmation endpoint (next module) additionally
   rejects the attempt before it ever reaches the database, so the failure
   the user sees is a clean 4xx rather than a raw constraint-violation error.

`confirmed_by` and `confirmed_at` are both nullable: a claim starts
`PENDING` with neither set, and both are populated together the instant a
different user confirms it.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import PaymentClaimStatus
from app.models.types import fk_uuid


class PaymentClaim(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "payment_claim"
    __table_args__ = (
        CheckConstraint(
            "confirmed_by IS NULL OR confirmed_by <> submitted_by",
            name="ck_payment_claim_distinct_submitter_confirmer",
        ),
    )

    finance_record_id: Mapped[uuid.UUID] = mapped_column(
        *fk_uuid("finance_record.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[PaymentClaimStatus] = mapped_column(
        Enum(PaymentClaimStatus, name="payment_claim_status", native_enum=True), nullable=False
    )

    submitted_by: Mapped[uuid.UUID] = mapped_column(*fk_uuid("user.id"), nullable=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(*fk_uuid("user.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    note: Mapped[str | None] = mapped_column(nullable=True)
