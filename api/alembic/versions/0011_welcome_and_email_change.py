"""welcome_and_email_change

Revision ID: 0011_welcome_and_email_change
Revises: 0010_password_reset_token
Create Date: 2026-09-27

Module 17: admin-created-user welcome email (no admin-supplied initial
password) and self-service email-change confirmation, both reusing
`password_reset_token`'s existing infrastructure rather than a parallel
mechanism.

1. `user.activated_at` (nullable) -- see `User`'s own docstring for the
   full reasoning. Backfilled to `created_at` for every existing row:
   every account seeded before this module (Module 11's manual seed,
   every Module-15-admin-created account) always had a real,
   admin-supplied password from the moment it was created, so none of
   them are genuinely "pending welcome activation" -- backfilling to
   `created_at` (a real, already-true timestamp for each of those rows,
   not an arbitrary placeholder) keeps the new column's own "has this
   account ever set a password" meaning consistent for every row that
   already exists, rather than leaving six-plus real, already-usable
   accounts looking newly-pending the moment this migration runs.

2. `password_reset_token.new_email` (nullable) -- see that model's own
   docstring for why this single column, not a second table, is enough
   to also carry Module 17's email-change confirmation tokens.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0011_welcome_and_email_change"
down_revision: str | None = "0010_password_reset_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("activated_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE \"user\" SET activated_at = created_at")

    op.add_column(
        "password_reset_token", sa.Column("new_email", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("password_reset_token", "new_email")
    op.drop_column("user", "activated_at")
