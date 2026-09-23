"""ImportBatch: one row per Excel import run.

Records who ran the import, when, against what source file, how many rows
it produced (broken down by outcome), and its outcome -- the audit trail
for "where did this applicant row come from," and the dedup key
(`checksum`) the import endpoint uses to short-circuit a re-upload of the
exact same file as a no-op.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, text
from sqlalchemy.dialects.postgresql import JSONB
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

    # sha256 hex digest of the uploaded file's raw bytes. See migration
    # 0008's own docstring for why this is a plain indexed column, not a
    # unique constraint -- a FAILED batch must not block retrying the
    # identical file.
    checksum: Mapped[str | None] = mapped_column(nullable=True)

    created_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    updated_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    flagged_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    rejected_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    flagged_rows: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    imported_by: Mapped[uuid.UUID] = mapped_column(*fk_uuid("user.id"), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
