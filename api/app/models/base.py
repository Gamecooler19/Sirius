"""SQLAlchemy declarative base and shared mixins.

Every business table gets:
- `id`: uuid primary key, defaulted server-side by `gen_random_uuid()`.
- `created_at` / `updated_at`: timestamptz, defaulted server-side by `now()`.
  `updated_at` is maintained by a trigger (see the audit migration), not by
  the ORM, so it stays correct even for a raw-SQL fix applied by hand.
"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
