"""Request/response schemas for the status-transition endpoint."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ApplicationStatus


class StatusTransitionRequest(BaseModel):
    to_status: ApplicationStatus
    note: str | None = None


class StatusTransitionResponse(BaseModel):
    applicant_id: uuid.UUID
    from_status: ApplicationStatus
    to_status: ApplicationStatus
    changed_by: uuid.UUID
    created_at: datetime
