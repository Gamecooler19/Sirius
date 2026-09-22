"""ApplicationStatusEvent: append-only log of every status transition an
applicant goes through. `applicant.current_status` is the fast-read
denormalization of "the latest one of these rows"; this table is the
authoritative history and is never updated or deleted after insert -- the
same append-only discipline `audit_log` enforces at the database via
trigger (see the append-only migration), applied here too since a status
history that can be silently edited after the fact is not a history.

`changed_by` is nullable only to allow a future system-initiated transition
(e.g. an automated timeout) with no human actor; every transition the next
module's status-endpoint creates will populate it.
"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.applicant import _status_enum
from app.models.base import Base, UUIDPKMixin
from app.models.enums import ApplicationStatus
from app.models.types import fk_uuid


class ApplicationStatusEvent(UUIDPKMixin, Base):
    __tablename__ = "application_status_event"

    applicant_id: Mapped[uuid.UUID] = mapped_column(*fk_uuid("applicant.id"), nullable=False)
    from_status: Mapped[ApplicationStatus | None] = mapped_column(_status_enum, nullable=True)
    to_status: Mapped[ApplicationStatus] = mapped_column(_status_enum, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(*fk_uuid("user.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
