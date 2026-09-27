"""Request/response schemas for the Excel-import endpoint."""

import uuid

from pydantic import BaseModel

from app.models.enums import ImportBatchStatus
from app.schemas._datetime import UtcDatetime


class ImportBatchResponse(BaseModel):
    id: uuid.UUID
    status: ImportBatchStatus
    row_count: int
    created_count: int
    updated_count: int
    flagged_count: int
    rejected_count: int
    flagged_rows: list[dict] | None
    error_detail: str | None
    completed_at: UtcDatetime | None
    deduplicated: bool = False
