"""Applicant: the core record this application tracks, imported from Excel
and then layered with status tracking and payment reconciliation on top.

`current_status` is a denormalized read of "the applicant's latest status"
-- the authoritative history lives in `application_status_event`
(append-only, one row per transition). Keeping a denormalized current value
on the parent row is a deliberate, ordinary tradeoff: every list/filter view
of applicants needs "what stage is this applicant at" without joining out to
the event log's latest row on every single list request, and the event log
remains the source of truth an audit or a status-correction always falls
back to.

`import_batch_id` traces every applicant row back to the Excel import that
created it (nullable: a future manually-created applicant, if that path is
ever added, would have no batch). `assigned_counselor_id` is nullable --
unassigned is a normal, expected state before a counselor picks up a new
inquiry.
"""

import uuid

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ApplicationStatus
from app.models.types import fk_uuid

_status_enum = Enum(ApplicationStatus, name="application_status", native_enum=True)


class Applicant(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "applicant"

    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        *fk_uuid("import_batch.id"), nullable=True
    )
    assigned_counselor_id: Mapped[uuid.UUID | None] = mapped_column(
        *fk_uuid("user.id"), nullable=True
    )

    full_name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)
    phone: Mapped[str | None] = mapped_column(nullable=True)
    program: Mapped[str] = mapped_column(nullable=False)
    intake_cycle: Mapped[str] = mapped_column(nullable=False)

    current_status: Mapped[ApplicationStatus] = mapped_column(_status_enum, nullable=False)
