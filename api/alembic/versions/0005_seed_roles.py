"""seed_roles

Revision ID: 0005_seed_roles
Revises: 0004_audit_trigger
Create Date: 2026-09-22

Seeds the six fixed roles this application recognizes (module scope). Uses
`code` (stable, machine-facing) as the idempotency key via
`ON CONFLICT (code) DO NOTHING` -- re-running this migration (or applying it
to a database that already has these rows from a prior partial run) is
therefore safe.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0005_seed_roles"
down_revision: str | None = "0004_audit_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    ("SUPER_ADMIN", "Super Admin", "Full system access; mandatory TOTP."),
    (
        "ADMISSIONS_MANAGER",
        "Admissions Manager",
        "Oversees admissions counselors and the full applicant pipeline.",
    ),
    (
        "ADMISSIONS_COUNSELOR",
        "Admissions Counselor",
        "Manages their own assigned applicants through the admissions pipeline.",
    ),
    ("FINANCE_STAFF", "Finance Staff", "Submits payment claims; mandatory TOTP."),
    (
        "FINANCE_MANAGER",
        "Finance Manager",
        "Confirms payment claims submitted by finance staff; mandatory TOTP.",
    ),
    ("AUDITOR", "Auditor", "Read-only visibility across admissions, finance, and audit_log."),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, name, description in ROLES:
        conn.execute(
            text(
                """
                INSERT INTO "role" (code, name, description)
                VALUES (:code, :name, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"code": code, "name": name, "description": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    codes = [code for code, _, _ in ROLES]
    conn.execute(
        text('DELETE FROM "role" WHERE code = ANY(:codes)'),
        {"codes": codes},
    )
