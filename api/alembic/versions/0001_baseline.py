"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-22

Empty baseline. No domain tables -- Module 01's real schema lands in the
next revision.
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
