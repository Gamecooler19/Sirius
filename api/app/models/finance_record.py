"""FinanceRecord: one-to-zero-or-one child of Applicant, created only once
an applicant's status reaches ADMISSION_TAKEN. The one-to-zero-or-one shape
is enforced by the unique constraint on `applicant_id` below; the "only
when status reaches Admission Taken" business rule is additionally enforced
at the database via a trigger (`finance_record_requires_admission_taken`,
see the schema migration) rather than left to application code alone --
consistent with this project's ADR-07 stance that a guarantee enforced only
by a service-layer check is one forgotten call path away from being wrong,
and a raw-SQL insert done by hand during an incident should not be able to
create an orphaned finance record for an applicant who never actually
reached that status.

This module creates the table so the next module's payment-workflow
endpoints have something to write balances and reconciliation state to; the
reconciliation logic itself is out of scope here.
"""

import uuid
from decimal import Decimal

from sqlalchemy import Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.types import fk_uuid


class FinanceRecord(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "finance_record"
    __table_args__ = (UniqueConstraint("applicant_id", name="uq_finance_record_applicant"),)

    applicant_id: Mapped[uuid.UUID] = mapped_column(*fk_uuid("applicant.id"), nullable=False)

    total_fee_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
