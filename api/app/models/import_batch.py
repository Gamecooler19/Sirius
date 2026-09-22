"""ImportBatch: one row per Excel import run.

Records who ran the import, when, against what source file, how many rows
it produced, and its outcome -- the audit trail for "where did this
applicant row come from" that the next module's Excel-import endpoint will
write to. This module creates the table only; the import logic itself is
out of scope here (see the module prompt).
"""

import uuid
from datetime import datetime

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.enums import ImportBatchStatus
from app.models.types import fk_uuid


class ImportBatch(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "import_batch"

    source_filename: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[ImportBatchStatus] = mapped_column(
        Enum(ImportBatchStatus, name="import_batch_status", native_enum=True), nullable=False
    )
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    error_detail: Mapped[str | None] = mapped_column(nullable=True)

    imported_by: Mapped[uuid.UUID] = mapped_column(*fk_uuid("user.id"), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
