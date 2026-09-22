"""Role: the six fixed roles this application recognizes.

Not RLS-scoped to anything else -- roles are a fixed catalogue seeded once
by migration, not per-tenant data. `code` is the stable, machine-facing
identifier RBAC and RLS policies key off (see `app.models.enums.RoleCode`);
`name` is the human-readable label a UI may display and could in principle
be edited without touching access-control logic.
"""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Role(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("code", name="uq_role_code"),)

    code: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
