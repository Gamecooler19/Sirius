"""AuditLog: a single generic audit table keyed by `table_name` +
`record_id`, rather than one audit table per entity -- every mutated table
in this schema writes into this one table via the same `write_audit()`
trigger (ADR-07), so adding a new audited table in a future module never
means adding a new audit table alongside it.

Written exclusively by the `write_audit()` Postgres trigger, never by
application code directly. UPDATE and DELETE against this table are blocked
by a second trigger (`audit_log_block_mutation`), not merely discouraged by
convention -- see the audit-trigger migration.

`actor_id`: `current_setting('app.actor_id', true)`, the authenticated
user's id for the request that caused the write; NULL for a write with no
authenticated actor (a migration-time seed, for instance).
`client_ip`: `current_setting('app.client_ip', true)`, the real client IP
the request-handling dependency sets via `SET LOCAL` for the transaction.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin
from app.models.types import fk_uuid


class AuditLog(UUIDPKMixin, Base):
    __tablename__ = "audit_log"

    table_name: Mapped[str] = mapped_column(nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(*fk_uuid("user.id"), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
