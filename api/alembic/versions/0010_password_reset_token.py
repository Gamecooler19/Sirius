"""password_reset_token

Revision ID: 0010_password_reset_token
Revises: 0009_payment_claim_workflow
Create Date: 2026-09-27

Module 16: self-service password reset. One new table,
`password_reset_token` -- deliberately joins `user`/`role`/
`user_backup_code` as an *unscoped* table (no RLS enabled at all), not
merely "gets the audit trigger's usual FK check." Both endpoints that
touch this table (`POST /auth/forgot-password`, `POST
/auth/reset-password`) are unauthenticated by definition -- that is the
entire point of a self-service reset flow a locked-out user can reach
without a session -- so there is no `app.actor_role`/`app.actor_id` GUC
set when either endpoint's queries run. This is structurally the same
reasoning migration `0003_rls`'s own docstring already gives for why
`user`/`role`/`user_backup_code` are excluded from RLS (ADR-03's
"identity axis"): a table an unauthenticated request must read or write
cannot be gated by a GUC only an authenticated request sets.

`token_hash` is hashed (argon2id, application-layer, the same hasher
`UserBackupCode.code_hash` already uses), never the raw token -- see the
model's own docstring. `used_at`/`expires_at` together make each token
single-use and time-limited, checked by the reset endpoint itself, not
by any database constraint (a CHECK constraint cannot reference `now()`
meaningfully for an expiry check the same way an application-layer
comparison can, and PostgreSQL does not support "insert-time" CHECK
constraints against volatile functions).

Gets both an audit trigger (`password_reset_token_write_audit`, same as
every other mutable business table -- ADR-07) and an index on
`user_id` (every real query against this table is
`WHERE user_id = :user_id`, either to find a pending token to send, or
implicitly via the token hash itself being looked up directly).
`user_backup_code` has the same index for the same query shape and was
the template followed here.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010_password_reset_token"
down_revision: str | None = "0009_payment_claim_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_token",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_token_hash"),
    )
    op.create_index(
        "ix_password_reset_token_user_id", "password_reset_token", ["user_id"]
    )

    # ADR-07: every mutable business table gets write_audit() -- the
    # function itself already exists (migration 0004), this just wires a
    # trigger for the new table onto it, the same one-line-per-table
    # pattern that migration already established.
    op.execute(
        """
        CREATE TRIGGER password_reset_token_write_audit
        AFTER INSERT OR UPDATE OR DELETE ON password_reset_token
        FOR EACH ROW EXECUTE FUNCTION write_audit()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS password_reset_token_write_audit ON password_reset_token")
    op.drop_index("ix_password_reset_token_user_id", table_name="password_reset_token")
    op.drop_table("password_reset_token")
