"""push_subscription

Revision ID: 0012_push_subscription
Revises: 0011_welcome_and_email_change
Create Date: 2026-09-27

Module 20: real Web Push notifications. One new table,
`push_subscription` -- deliberately joins `user`/`role`/
`user_backup_code`/`password_reset_token` as an *unscoped* table (no RLS
enabled), for the same "identity axis" reasoning as those tables -- see
`app.models.push_subscription`'s own docstring for the full account of
why an RLS policy here would either silently drop legitimate
system-triggered notification reads or need the same per-call elevated-
scope workaround Module 19's duplicate-detection fix already
established, applied at the wrong granularity (a whole table, not one
query).

`endpoint` is `UNIQUE` -- the subscribe endpoint upserts on a collision
(the same browser re-subscribing returns the identical `endpoint` value
from `pushManager.subscribe()`), never creates a second row for what is,
from the push service's own point of view, the same subscription.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0012_push_subscription"
down_revision: str | None = "0011_welcome_and_email_change"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscription",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
    )
    op.create_index(
        "ix_push_subscription_user_id", "push_subscription", ["user_id"]
    )

    # ADR-07: every mutable business table gets write_audit() -- reused
    # verbatim, the same one-line-per-table pattern every prior migration
    # has followed.
    op.execute(
        """
        CREATE TRIGGER push_subscription_write_audit
        AFTER INSERT OR UPDATE OR DELETE ON push_subscription
        FOR EACH ROW EXECUTE FUNCTION write_audit()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS push_subscription_write_audit ON push_subscription")
    op.drop_index("ix_push_subscription_user_id", table_name="push_subscription")
    op.drop_table("push_subscription")
