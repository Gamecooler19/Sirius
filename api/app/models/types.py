"""Small typing helpers shared across models."""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID


def fk_uuid(target: str) -> tuple:
    """Returns the (type, ForeignKey) pair for a `Mapped[uuid.UUID]` column
    referencing `target` (e.g. "users.id"), so every FK column doesn't repeat
    the same `UUID(as_uuid=True), ForeignKey(...)` boilerplate.
    """
    return (UUID(as_uuid=True), ForeignKey(target))


__all__ = ["fk_uuid", "uuid"]
